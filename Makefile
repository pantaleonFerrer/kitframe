COMPOSE=docker compose -f infra/docker/docker-compose.yml
# Load repo .env into make recipes without overriding already-exported vars
ENV_FILE=.env
LOAD_ENV=set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a

.PHONY: up down migrate seed seed-media api worker web dev demo test wait-db

up:
	@docker info >/dev/null 2>&1 || (echo "Docker Desktop no está arrancado. Ábrelo y reintenta."; exit 1)
	$(COMPOSE) up -d postgres minio minio-init mailpit
	@$(MAKE) wait-db

wait-db:
	@echo "Esperando Postgres en :5433…"
	@for i in $$(seq 1 30); do \
		if $(COMPOSE) exec -T postgres pg_isready -U kitframe -d kitframe >/dev/null 2>&1; then \
			echo "Postgres listo."; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Postgres no responde. Revisa: $(COMPOSE) logs postgres"; \
	exit 1

down:
	$(COMPOSE) down

# One terminal: infra + migrate/seed + api + worker + web. Ctrl+C stops app processes.
dev:
	bash scripts/dev.sh

# Demo stack: respects .env (BFL + AWS S3). Does not force fake/MinIO.
demo:
	bash scripts/demo.sh

migrate: wait-db
	@$(LOAD_ENV); cd apps/api && (test -d .venv || python3 -m venv .venv) && . .venv/bin/activate && \
		pip install -e ".[dev]" -q && \
		kitframe migrate

seed: wait-db
	@$(LOAD_ENV); cd apps/api && . .venv/bin/activate && \
		SEED_PASSWORDS=$${SEED_PASSWORDS:-true} \
		kitframe seed
	@echo "Users: owner@kitframe.local … Password: Kitframe-dev-2026!"
	@echo "Seed media: fixtures uploaded to S3/MinIO under seed/…"

seed-media:
	@$(LOAD_ENV); cd apps/api && . .venv/bin/activate && \
		python -c "from kitframe.settings import get_settings; get_settings.cache_clear(); from kitframe.db.seed_media import upload_seed_media; upload_seed_media()"


api:
	@$(LOAD_ENV); cd apps/api && . .venv/bin/activate && \
		kitframe api --host 0.0.0.0 --port 8080

worker:
	@$(LOAD_ENV); cd apps/api && . .venv/bin/activate && \
		kitframe worker

web:
	cd apps/web && pnpm install && pnpm dev

test:
	cd apps/api && . .venv/bin/activate && pytest -q --cov=kitframe/workflow --cov=kitframe/auth --cov=kitframe/qc --cov=kitframe/studio --cov=kitframe/shopify || pytest -q
	cd apps/web && pnpm install && pnpm lint && pnpm exec tsc --noEmit
