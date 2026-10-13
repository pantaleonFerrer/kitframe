# Kitframe

Product data, creative workflow and AI image production for FC Barcelona merchandising. Built by Gathered. Spec: [docs/BUILD_SPEC.md](docs/BUILD_SPEC.md).

## Architecture (v4.1)

```
Browser → web (Next.js) → api (Python FastAPI)
                              ↓
                         worker (same package, Procrastinate/Postgres jobs)
                              ↓
                    Postgres 16 + S3-compatible storage
```

## Local development

**Una sola terminal** (recomendado):

```bash
cp .env.example .env   # solo la primera vez
make dev               # Ctrl+C para parar api/worker/web
```

Equivale a subir Docker (Postgres/MinIO/Mailpit), migrar, seedear y arrancar api + worker + web en foreground.

**Tres terminales** (si lo prefieres):

```bash
make up && make migrate && make seed
make api      # terminal 1
make worker   # terminal 2
make web      # terminal 3
```

- Web: http://localhost:3000
- API: http://localhost:8080/api/v1
- Mailpit: http://localhost:8025

Seed users (password `Kitframe-dev-2026!`): `owner@kitframe.local`, `admin@kitframe.local`, `datos@kitframe.local`, `creativo@kitframe.local`, `diseno@kitframe.local`, `revisor@kitframe.local`, `viewer@kitframe.local`.

Para bajar también Docker: `make down`.

## Providers (BUILD_SPEC 4.1)

| Role | Production | Local/test |
|---|---|---|
| Images | **BFL FLUX.2** (`bfl`, EU `api.eu.bfl.ai`) | `fake` |
| LLM | **Mistral** (`mistral-large-2512`) | `fake` |

Set `BFL_API_KEY`, `BFL_API_BASE_URL`, `MISTRAL_API_KEY`, `MISTRAL_API_BASE_URL`. Staging/production refuse `fake` and non-EU BFL hosts at startup. Spike: `scripts/spike_flux2.py`.

## Deploy (Hetzner)

Same VPS as gathered-brain: Docker Compose + **host Nginx** (no Caddy). Guide: [infra/DEPLOY.md](infra/DEPLOY.md).

```bash
# on the server → /opt/kitframe
cp infra/env/production.example .env   # fill secrets + DOMAIN
# enable infra/nginx/kitframe.conf in host Nginx, then:
IMAGE_TAG=<git-sha> ./scripts/deploy.sh
```

Loopback ports: API `127.0.0.1:18080`, web `127.0.0.1:13000` (gathered keeps `:8080`).

## Legacy

Previous Go API + ai-service live under `legacy/` for reference only and are not deployed.
