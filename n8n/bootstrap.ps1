# KYRO n8n bootstrap — idempotently imports the committed workflow export.
# Usage (from repo root, Stack A running):
#   powershell -ExecutionPolicy Bypass -File n8n\bootstrap.ps1
#
# v2 (security remediation, Group C): the workflow now verifies GitHub's
# X-Hub-Signature-256 HMAC against $KYRO_WEBHOOK_SECRET and rejects unsigned /
# invalid deliveries with 401 BEFORE anything is published to Kafka.
# This script therefore also:
#   - refuses to run when KYRO_WEBHOOK_SECRET is missing from the container env
#   - force re-imports the workflow (delete + import) so edits always land
param(
    [string]$Container = "kyro-n8n",
    [string]$WorkflowFile = "$PSScriptRoot\workflows\kyro-github-webhook.json",
    [string]$WorkflowId = "mlEODTybeNYN2wzq"
)

$ErrorActionPreference = "Stop"

# 1. Container must be up (Stack A: infra/docker-compose.yml).
$running = docker ps --filter "name=$Container" --format "{{.Names}}"
if ($running -ne $Container) {
    Write-Error "Container '$Container' is not running. Start Stack A first: docker compose -f infra/docker-compose.yml up -d"
    exit 1
}

# 2. HMAC secret must be present in the container env (fail closed without it).
$secret = docker exec $Container printenv KYRO_WEBHOOK_SECRET 2>$null
if (-not $secret) {
    Write-Error "KYRO_WEBHOOK_SECRET is not set in '$Container'. Set it in the root .env (see .env.example), then re-create stack A: docker compose -f infra/docker-compose.yml up -d"
    exit 1
}

# 3. Export must exist.
if (-not (Test-Path $WorkflowFile)) {
    Write-Error "Export not found: $WorkflowFile"
    exit 1
}

# 4. Force re-import: n8n CLI cannot upsert by id, so remove the previous
#    copy first (the authoritative export lives in git). Ignore errors when
#    the workflow is absent on a fresh instance.
$existing = docker exec $Container n8n list:workflow 2>$null
if ($existing -match [regex]::Escape($WorkflowId)) {
    Write-Host "[bootstrap] removing previous import of $WorkflowId for re-import..."
    $tmp = [System.IO.Path]::GetTempFileName()
    docker exec $Container n8n export:workflow --id=$WorkflowId --output=/tmp/kyro-old.json | Out-Null
    docker cp "${Container}:/tmp/kyro-old.json" $tmp | Out-Null
    $old = Get-Content $tmp -Raw | ConvertFrom-Json
    Remove-Item $tmp -Force
    $oldId = $old.id
    docker exec $Container n8n delete:workflow --id=$oldId 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[bootstrap] delete:workflow not available - importing may create a duplicate id."
    }
}

docker cp $WorkflowFile "${Container}:/tmp/kyro-workflow.json" | Out-Null
docker exec $Container n8n import:workflow --input=/tmp/kyro-workflow.json
if ($LASTEXITCODE -ne 0) { Write-Error "workflow import failed"; exit 1 }
Write-Host "[bootstrap] workflow imported."

# 5. Resolve the actual workflow id (list format: "<id>|<name>") and activate it.
$imported = docker exec $Container n8n list:workflow 2>$null | Select-String "KYRO-N8N"
if (-not $imported) { Write-Error "imported workflow not found"; exit 1 }
$line = ($imported | Select-Object -First 1).Line.Trim()
$newId = ($line -split "\|")[0].Trim()
docker exec $Container n8n update:workflow --id=$newId --active=true
if ($LASTEXITCODE -ne 0) { Write-Error "activation failed for $newId"; exit 1 }
Write-Host "[bootstrap] workflow $newId activated."

# 6. Publish + activate, then restart so n8n registers the webhook "active
#    version" (n8n 2.x serves the PUBLISHED version only; CLI activation
#    alone leaves the route answering 404/200 with the old definition).
docker exec $Container n8n publish:workflow --id=$newId
if ($LASTEXITCODE -ne 0) { Write-Error "publish failed for $newId"; exit 1 }
docker exec $Container n8n update:workflow --id=$newId --active=true 2>$null | Out-Null
Write-Host "[bootstrap] workflow $newId published + activated."

# 6b. Restart: publish/activate only take effect after n8n reloads (CLI says
#     "Changes will not take effect if n8n is running"). One container, light.
docker restart $Container | Out-Null
foreach ($i in 1..30) {
    $hz = curl.exe -s -m 3 http://localhost:5678/healthz 2>$null
    if ($hz -eq "ok") { break }
    Start-Sleep 4
}
Write-Host "[bootstrap] $Container restarted, healthz=$hz."

# 7. Credential sanity check: this n8n build has no `list:credential` CLI
#    command, so verify the Kafka Publish node carries a linked credential
#    id instead (the secret itself is encrypted inside the n8n volume).
$export = [System.IO.Path]::GetTempFileName()
docker exec $Container n8n export:workflow --id=$newId --output=/tmp/kyro-check.json | Out-Null
docker cp "${Container}:/tmp/kyro-check.json" $export | Out-Null
$wf = Get-Content $export -Raw | ConvertFrom-Json
Remove-Item $export -Force
$kafkaNode = $wf.nodes | Where-Object { $_.type -eq "n8n-nodes-base.kafka" } | Select-Object -First 1
if ($kafkaNode -and $kafkaNode.credentials) {
    Write-Host "[bootstrap] Kafka Publish credential linked: $($kafkaNode.credentials.PSObject.Properties.Name -join ', ')"
} else {
    Write-Warning "[bootstrap] Kafka Publish node has NO linked credential - re-link 'Kafka local' in the n8n UI (see n8n/README.md step 4)."
}

Write-Host "[bootstrap] done. Webhook: http://localhost:5678/webhook/github (HMAC-verified)"
