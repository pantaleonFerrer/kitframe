# Deploy

Full guide: [infra/DEPLOY.md](../../infra/DEPLOY.md).

Same as gathered-brain: build on the Hetzner host with Docker Compose (no GHCR).

1. Green **ci** on `main` triggers **Deploy Hetzner** (or run it manually).
2. SSH → `git reset --hard <sha>` → `./scripts/deploy.sh` (build, migrate, up).
3. Nginx vhost: `infra/nginx/kitframe.conf` → `127.0.0.1:18080` / `:13000`.
4. Smoke: `GET /api/v1/healthz`, login, `/tareas`.

# Rollback

`git reset --hard` to previous SHA (see `.deploy-previous-sha`) and run `./scripts/deploy.sh` again.
