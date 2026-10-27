$repo = "D:\projects\professional\KYRO\KYRO-Knowledge-driven-Yield-Repository-Optimization"
Set-Location $repo
docker info *> $null
if ($LASTEXITCODE -ne 0) { if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") { Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" }; foreach ($i in 1..60) { Start-Sleep -Seconds 3; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } } }
docker info *> $null
if ($LASTEXITCODE -eq 0) {
  docker compose -f infra/docker-compose.yml --env-file .env up -d --wait
  Set-Location "$repo\backend"
  .venv\Scripts\python.exe -m alembic upgrade head
  Set-Location $repo
  try { $beUp = ((Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) } catch { $beUp = $false }
  if (-not $beUp) { Start-Process cmd -ArgumentList "/k",".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$repo\backend" }
  $wk = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue | Where-Object { $_.CommandLine -like '*app.worker_main*' }
  if (-not $wk) { Start-Process cmd -ArgumentList "/k",".venv\Scripts\python.exe -m app.worker_main" -WorkingDirectory "$repo\backend" }
  try { $feUp = ((Invoke-WebRequest "http://127.0.0.1:3001/" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) } catch { $feUp = $false }
  if (-not $feUp) { Start-Process cmd -ArgumentList "/k","npm run dev" -WorkingDirectory "$repo\frontend" }
  $beOk = $false; $feOk = $false
  foreach ($i in 1..60) {
    try { if ((Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $beOk = $true } } catch {}
    try { if ((Invoke-WebRequest "http://127.0.0.1:3001/" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $feOk = $true } } catch {}
    if ($beOk -and $feOk) { break }
    Start-Sleep -Seconds 3
  }
  if ($beOk -and $feOk) { Write-Host ""; Write-Host "KYRO is UP  ->  http://127.0.0.1:3001" -ForegroundColor Green } else { Write-Host ""; Write-Host "NOT READY - backend=$beOk frontend=$feOk - check the three opened windows for errors" -ForegroundColor Red }
  if ($beOk -and $feOk) {
    $router = "$repo\scripts\public_router.mjs"
    if (-not (Get-NetTCPConnection -LocalPort 8090 -State Listen -EA SilentlyContinue)) { Start-Process node -ArgumentList "`"$router`"" -WindowStyle Hidden }
    $tunnelLog = "$env:TEMP\opencode\kyro_tunnel.log"
    $tunnelErr = "$env:TEMP\opencode\kyro_tunnel.err.log"
    if (-not (Get-Process cloudflared -EA SilentlyContinue)) {
      $cf = "D:\projects\professional\KYRO\cloudflared\cloudflared.exe"
      if (Test-Path $cf) {
        Remove-Item $tunnelLog,$tunnelErr -EA SilentlyContinue
        Start-Process $cf -ArgumentList "tunnel","--url","http://127.0.0.1:8090","--no-autoupdate" -RedirectStandardOutput $tunnelLog -RedirectStandardError $tunnelErr -WindowStyle Hidden
      } else { Write-Host "cloudflared.exe missing at $cf - public URL skipped" -ForegroundColor Yellow }
    }
    $kyroUrl = $null
    foreach ($i in 1..40) {
      if ($kyroUrl) { break }
      foreach ($f in @($tunnelLog,$tunnelErr)) { if (Test-Path $f) { $m = Select-String -Path $f -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -EA SilentlyContinue | Select-Object -First 1; if ($m) { $kyroUrl = $m.Matches[0].Value; break } } }
      if (-not $kyroUrl) { Start-Sleep -Seconds 1 }
    }
    if ($kyroUrl) {
      Write-Host ""
      Write-Host "KYRO public -> $kyroUrl" -ForegroundColor Green
      Write-Host "Syncing the GitHub App WEBHOOK URL to this tunnel URL (automatic, every run)..." -ForegroundColor Yellow
      & "$repo\backend\.venv\Scripts\python.exe" "$repo\scripts\sync_github_urls.py" $kyroUrl
      if ($LASTEXITCODE -ne 0) { Write-Host "Webhook auto-sync failed (offline? key rotated?). Set it by hand on the GitHub App settings page: $kyroUrl/webhook/github" -ForegroundColor Red }
      Write-Host "Webhook URL re-synced automatically - no GitHub edits needed when the tunnel changes." -ForegroundColor Green
      Write-Host "(OAuth callbacks cannot be set via API: laptop sign-in uses http://127.0.0.1:3001/.../callback - configured once, never changes. A tunnel callback is only needed for phone demos.)" -ForegroundColor DarkGray
    } else { Write-Host ""; Write-Host "Tunnel URL not found yet - check $tunnelLog" -ForegroundColor Yellow }
  }
} else {
  Write-Host "Docker Desktop did not start - open it manually, then run startup.ps1 again." -ForegroundColor Red
}
