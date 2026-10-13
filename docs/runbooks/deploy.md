# Deploy

1. CI builds images tagged with git SHA
2. `alembic upgrade head` on target env
3. Roll out api ×2, worker ×1, web ×1
4. Smoke: `/api/v1/readyz`, login, load `/tareas`

# Rollback

Redeploy previous image SHA without running destructive migrations (expand/contract only).
