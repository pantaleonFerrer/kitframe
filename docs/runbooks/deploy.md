# Deploy

Full guide: [infra/DEPLOY.md](../../infra/DEPLOY.md).

Co-hosted with gathered-brain on the same Hetzner VPS. Host Nginx terminates TLS; Kitframe Compose binds only `127.0.0.1:18080` (api) and `127.0.0.1:13000` (web).

1. CI **images** → GHCR (`kitframe-api` / `kitframe-web` @ git SHA).
2. Enable `infra/nginx/kitframe.conf` on the host.
3. `IMAGE_TAG=<sha> ./scripts/deploy.sh` in `/opt/kitframe`.
4. Smoke: `GET /api/v1/healthz`, login, `/tareas`.

# Rollback

Redeploy previous image SHA without destructive migrations.
