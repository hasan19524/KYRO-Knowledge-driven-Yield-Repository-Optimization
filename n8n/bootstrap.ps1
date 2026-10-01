# KYRO n8n bootstrap — idempotently imports the committed workflow export.
# Usage (from repo root, Stack A running):
#   powershell -ExecutionPolicy Bypass -File n8n\bootstrap.ps1
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

# 2. Skip import if the workflow already exists in this n8n instance.
$existing = docker exec $Container n8n list:workflow 2>$null
if ($existing -match [regex]::Escape($WorkflowId)) {
    Write-Host "[bootstrap] workflow $WorkflowId already present - nothing to do."
} else {
    if (-not (Test-Path $WorkflowFile)) {
        Write-Error "Export not found: $WorkflowFile"
        exit 1
    }
    docker cp $WorkflowFile "${Container}:/tmp/kyro-workflow.json" | Out-Null
    docker exec $Container n8n import:workflow --input=/tmp/kyro-workflow.json
    if ($LASTEXITCODE -ne 0) { Write-Error "workflow import failed"; exit 1 }
    Write-Host "[bootstrap] workflow imported."
}

# 3. Credential sanity check.
# The Kafka Publish node references credential name 'Kafka local'
# (id kafkaLocalKyro01). Credentials are ENCRYPTED inside the n8n volume and
# are deliberately NOT part of this repo - on a fresh instance create it once
# in the UI: Credentials -> New -> Kafka -> bootstrapServers: kyro-kafka:29092,
# security: plaintext, then re-open the workflow and re-select it on the
# 'Kafka Publish' node. Existing volume: already present, nothing to do.
$creds = docker exec $Container n8n list:credential 2>$null
if ($creds -match "Kafka local") {
    Write-Host "[bootstrap] credential 'Kafka local' present."
} else {
    Write-Warning "[bootstrap] credential 'Kafka local' MISSING - create it in the n8n UI (see n8n/README.md step 4) and re-link the Kafka Publish node."
}

# 4. Activate if imported inactive (export carries active=true, but be safe).
$wf = docker exec $Container n8n list:workflow 2>$null | Select-String $WorkflowId
if ($wf -and ($wf -notmatch "\(active\)")) {
    docker exec $Container n8n update:workflow --id=$WorkflowId --active=true
    Write-Host "[bootstrap] workflow activated."
}

Write-Host "[bootstrap] done. Webhook: http://localhost:5678/webhook/github"
