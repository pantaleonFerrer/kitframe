# Incident response

## Severity

| Level | Meaning | Response |
|---|---|---|
| SEV1 | Full outage, data loss risk, or security breach | Page on-call immediately; all hands until mitigated |
| SEV2 | Major feature broken (board, publish, generation) | Respond within 30 minutes |
| SEV3 | Degraded performance or partial failure | Business hours; track to fix |

## First 15 minutes

1. Declare severity in the ops channel; assign an incident commander.
2. Check Hetzner status and host reachability for `api`, `ai`, `worker`, `web`, `data`.
3. Check API `/healthz`, AI `/healthz`, worker queue depth, Postgres connections, MinIO.
4. If data integrity is in doubt, freeze writes (stop worker and API write paths) before repair.
5. Capture timestamps, failing SHA, and recent deploys.

## Common failure modes

### API unavailable

- Confirm both API replicas and load balancer targets.
- Roll back to previous image tag via `.github/workflows/deploy.yml` if a bad deploy is suspected.
- Check Postgres connectivity from private network `10.0.1.0/24`.

### Generation / QC stuck

- Confirm AI replicas and optional Ollama GPU host.
- Check Fal.ai status if `GENERATION_PROVIDER=fal`.
- Drain and restart the worker; inspect dead-letter / failed River jobs.

### Data host failure

- Follow [backup-restore.md](./backup-restore.md).
- RPO target 24h; RTO target 4h.

### Suspected compromise

- Rotate JWT secrets, DB password, MinIO keys, Fal key, Shopify webhook secret.
- Revoke SSH keys; rebuild from known-good images.
- Preserve disk snapshots for forensics before wipe.

## Communications

- Internal: ops channel every 15 minutes during SEV1.
- Client: only after commander approval; stick to impact, mitigation, next update time.
- Never share credentials or raw dumps in chat.

## Close-out

1. Confirm user-visible recovery with smoke checks.
2. Write a short timeline: detect → mitigate → resolve.
3. File follow-ups (alerts, runbook gaps, code fixes).
4. Schedule a restore drill if the incident involved backup or data recovery.
