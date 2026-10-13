# Deploy Kitframe on Hetzner (Docker Compose)

Same VPS as **gathered-brain** (`/opt/gathered-brain`). Host **Nginx** already owns `:80`/`:443` and gathered API is on `127.0.0.1:8080`. Kitframe does **not** run Caddy; it publishes only loopback ports and gets a separate Nginx `server_name`.

```
Internet → Nginx :443
             ├─ brain / api.gathered.so  → 127.0.0.1:8080   (gathered)
             └─ kitframe.DOMAIN          → 127.0.0.1:13000  (web)
                                         → 127.0.0.1:18080  (api /api/*)

/opt/gathered-brain   compose project: gathered
/opt/kitframe         compose project: kitframe  (own Postgres volume)
```

## 1. Bootstrap (if `/opt/kitframe` does not exist)

Docker is probably already installed. As root:

```bash
export DEPLOY_REPO=https://github.com/YOUR_ORG/kitframe.git
export DOMAIN=kitframe.example.com
bash /path/to/kitframe/scripts/hetzner-bootstrap.sh
# or clone then run the script
```

Creates `/opt/kitframe` and `.env` from `infra/env/production.example`. Does not touch gathered-brain or rebind 80/443.

## 2. Secrets

```bash
ssh user@SERVER
cd /opt/kitframe
$EDITOR .env
```

Set `DOMAIN`, `POSTGRES_PASSWORD`, JWT/encryption keys, S3, BFL, Mistral, `GHCR_OWNER`.  
Postgres password should be URL-safe (compose builds `DATABASE_URL`).

Optional port overrides (defaults avoid gathered’s `8080`):

```bash
KITFRAME_API_HOST_PORT=18080
KITFRAME_WEB_HOST_PORT=13000
```

Private GHCR: `docker login ghcr.io`.

## 3. Nginx vhost

```bash
sudo cp /opt/kitframe/infra/nginx/kitframe.conf /etc/nginx/sites-available/kitframe
sudo sed -i 's/kitframe.example.com/YOUR_REAL_DOMAIN/g' /etc/nginx/sites-available/kitframe
sudo ln -sf /etc/nginx/sites-available/kitframe /etc/nginx/sites-enabled/kitframe
sudo certbot --nginx -d YOUR_REAL_DOMAIN
sudo nginx -t && sudo systemctl reload nginx
```

DNS `A`/`AAAA` for the Kitframe domain → same server IP as gathered.

## 4. Images + deploy

CI **images** on `main` → `ghcr.io/<owner>/kitframe-api:<sha>` and `kitframe-web:<sha>`.

```bash
cd /opt/kitframe
export IMAGE_TAG=<git-sha>
./scripts/deploy.sh
```

Or GitHub **deploy** workflow (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `APP_URL`).

## 5. Smoke

```bash
curl -fsS http://127.0.0.1:18080/api/v1/healthz
curl -fsS https://YOUR_DOMAIN/api/v1/healthz
curl -fsS -o /dev/null -w "%{http_code}\n" https://YOUR_DOMAIN/
```

## Coexistence checklist

| | gathered-brain | kitframe |
|---|---|---|
| Path | `/opt/gathered-brain` | `/opt/kitframe` |
| Compose `name` | `gathered` | `kitframe` |
| Host API port | `127.0.0.1:8080` | `127.0.0.1:18080` |
| Host web port | (Vercel / other) | `127.0.0.1:13000` |
| TLS | host Nginx | same Nginx, new `server_name` |
| DB | external / shared infra | **own** Postgres container + volume |

Do not publish Kitframe on host `:8080` or run a second reverse proxy on `:80`/`:443`.

## Useful commands

```bash
cd /opt/kitframe
docker compose -f infra/docker/docker-compose.prod.yml --env-file .env ps
docker compose -f infra/docker/docker-compose.prod.yml --env-file .env logs -f api worker web
```

## Rollback

Redeploy a previous `IMAGE_TAG`. No destructive migrations.
