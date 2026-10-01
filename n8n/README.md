# KYRO n8n — GitHub webhook → Kafka translator

n8n receives GitHub push webhooks, normalizes the payload (event envelope,
repository, actor, push metadata, commits), optionally calls the backend over
HTTP, and publishes to Kafka topic `kyro.github.push`.

## Files

| File | Purpose |
|---|---|
| `workflows/kyro-github-webhook.json` | Full export of workflow `mlEODTybeNYN2wzq` ("KYRO-N8N"), `active: true`. Committed — no secrets inside (credentials are referenced by name/id only). |
| `bootstrap.ps1` | Idempotent import into a running `kyro-n8n` container (safe to re-run; skips when already present). |

## Runtime contract (locked)

- Webhook: `POST http://localhost:5678/webhook/github` (GitHub App points here)
- Producer: topic `kyro.github.push`, key = `repository.github_id`
- n8n Kafka acks = 1 (known limitation — do not "fix" without reading the audit)
- Kafka bootstrap from containers: `kyro-kafka:29092` (Stack A network)

## Fresh-deploy procedure

1. Start Stack A: `docker compose -f infra/docker-compose.yml up -d`
2. Import: `powershell -ExecutionPolicy Bypass -File n8n\bootstrap.ps1`
3. Open http://localhost:5678 (owner account on first run).
4. **Only on a fresh n8n volume**: create credential `Kafka local`
   (Credentials → New → Kafka → `bootstrapServers: kyro-kafka:29092`,
   plaintext, no SASL), then open the workflow and re-select it on the
   *Kafka Publish* node. Credentials are encrypted inside volume `n8n_data`
   and are intentionally never committed to git.
5. Verify workflow shows *Active* and webhook test returns 200.

## Notes

- The n8n image is digest-pinned in `infra/docker-compose.yml`; the encryption
  key lives inside volume `n8n_data` (`/home/node/.n8n/config`) — never set a
  different `N8N_ENCRYPTION_KEY` for this volume or stored credentials stop
  decrypting.
- Only the KYRO workflow is committed. This n8n instance may host unrelated
  personal workflows — they are exported locally but never added to this repo.
