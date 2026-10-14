# Deploy Kitframe on Hetzner (Docker Compose)

Same pattern as **gathered-brain**: git pull on the VPS → `docker compose build` → migrate → `up -d`. No container registry.

Same VPS as gathered-brain (`/opt/gathered-brain`). Host **Nginx** owns `:80`/`:443`; gathered API is on `127.0.0.1:8080`. Kitframe publishes only loopback ports.

```
Internet → Nginx :443
             ├─ brain / api.gathered.so  → 127.0.0.1:8080   (gathered)
             └─ kitframe.DOMAIN          → 127.0.0.1:13000  (web)
                                         → 127.0.0.1:18080  (api /api/*)

/opt/gathered-brain   compose project: gathered
/opt/kitframe         compose project: kitframe
Postgres              externo (mismo que gathered; DB/usuario `kitframe` propios)
```

## 1. Bootstrap

```bash
sudo mkdir -p /opt/kitframe && sudo chown "$USER:$USER" /opt/kitframe
git clone git@github.com:YOUR_ORG/kitframe.git /opt/kitframe
cd /opt/kitframe
cp infra/env/production.example .env
$EDITOR .env
```

Or run `scripts/hetzner-bootstrap.sh` as root with `DEPLOY_REPO` / `DOMAIN` set.

## 2. Postgres externo

Crea DB y usuario **kitframe** (no uses la DB de gathered):

```bash
sudo -u postgres createuser kitframe
sudo -u postgres createdb -O kitframe kitframe
sudo -u postgres psql -c "ALTER USER kitframe PASSWORD '…';"
```

En `.env`:

```bash
# Postgres en el mismo host:
DATABASE_URL=postgresql+asyncpg://kitframe:…@host.docker.internal:5432/kitframe
```

Asegúrate de que Postgres acepta conexiones desde Docker (p. ej. escucha en `*`, o al menos alcanzable vía `host.docker.internal`).

## 3. Secrets (`.env`)

Required: `DOMAIN`, `DATABASE_URL`, `JWT_SECRET` (≥32), `APP_ENCRYPTION_KEY`, S3, `BFL_API_KEY`, `MISTRAL_API_KEY`.

Ports (defaults avoid gathered’s `8080`):

```bash
KITFRAME_API_HOST_PORT=18080
KITFRAME_WEB_HOST_PORT=13000
```

## 4. Nginx vhost

```bash
sudo cp /opt/kitframe/infra/nginx/kitframe.conf /etc/nginx/sites-available/kitframe
sudo sed -i 's/kitframe.example.com/YOUR_REAL_DOMAIN/g' /etc/nginx/sites-available/kitframe
sudo ln -sf /etc/nginx/sites-available/kitframe /etc/nginx/sites-enabled/kitframe
sudo certbot --nginx -d YOUR_REAL_DOMAIN
sudo nginx -t && sudo systemctl reload nginx
```

## 5. GitHub (CD)

Environment **production** secrets (same names as gathered-brain):

| Secret | Purpose |
|---|---|
| `HETZNER_HOST` | VPS IP/hostname |
| `HETZNER_USER` | SSH user |
| `HETZNER_SSH_KEY` | Private key |
| `HETZNER_DEPLOY_PATH` | Optional; default `/opt/kitframe` |

Workflow **Deploy Hetzner** runs after green **ci** on `main`, or manually via `workflow_dispatch`.

On the server it does: `git reset --hard <sha>` → `./scripts/deploy.sh` (build + migrate + up).

## 6. Manual deploy

```bash
cd /opt/kitframe
git pull   # or reset --hard <sha>
./scripts/deploy.sh
```

## 7. Smoke

```bash
curl -fsS http://127.0.0.1:18080/api/v1/healthz
curl -fsS https://YOUR_DOMAIN/api/v1/healthz
```

## Coexistence

| | gathered-brain | kitframe |
|---|---|---|
| Path | `/opt/gathered-brain` | `/opt/kitframe` |
| Compose | `gathered` | `kitframe` |
| Host API | `127.0.0.1:8080` | `127.0.0.1:18080` |
| Host web | (Vercel / other) | `127.0.0.1:13000` |
| Images | build on server | build on server |
| Postgres | externo | externo (DB `kitframe` aparte) |
| TLS | host Nginx | same Nginx, new `server_name` |
