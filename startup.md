# KYRO — single-command launcher

**Run this (copy-paste into PowerShell):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\projects\professional\KYRO\KYRO-Knowledge-driven-Yield-Repository-Optimization\startup.ps1"
```

That one command starts everything and keeps it consistent:

1. Docker Desktop (if not running) → `docker compose up -d --wait` (postgres, chroma, kafka, n8n — volumes preserved)
2. `alembic upgrade head`
3. Backend `:8000` (uvicorn), worker (Kafka consumer), frontend `:3001` (Next dev) — each only if not already up
4. Public router `:8090` + Cloudflare quick tunnel
5. Reads the fresh tunnel URL and **auto-syncs the GitHub App webhook URL to it via the GitHub API** (`scripts/sync_github_urls.py`, authenticated with the App's own key) — so a new tunnel URL needs **no GitHub settings edits**

Safe to re-run any time: every step is idempotent (already-running services are left alone, the webhook sync is a no-op when the URL is unchanged).

**One-time GitHub App setup** (only ever again if you regenerate secrets):

- Authorization callback URLs (Settings → OAuth):
  - `http://127.0.0.1:3001/backend/api/auth/github/callback` ← laptop sign-in; never changes
  - (phone demo only) the current tunnel URL + `/backend/api/auth/github/callback` — GitHub has **no API** for callback URLs, so this one is manual when you want a demo from another device
- Webhook URL: managed automatically by the launcher; no manual edits needed

**When you see the launcher output:** `KYRO is UP -> http://127.0.0.1:3001` plus `KYRO public -> https://...trycloudflare.com`, everything is ready. Open the local URL (or the public one from another device) and sign in.

Troubleshooting: `docs/OPERATIONS.md` §2 (start) and §8 (symptom table). The launcher prints the tunnel log path if the public URL doesn't appear.
