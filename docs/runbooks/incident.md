# Incident response

1. Check `/api/v1/readyz` and queue depth (`/metrics`)
2. Inspect failed jobs in Ajustes → Trabajos fallidos
3. For publish failures, retry from product Publicación tab
4. Escalate to Gathered on-call if `/readyz` fails 3 minutes
