# Backup and restore

## Objectives

| Metric | Target |
|---|---|
| RPO | 24 hours (daily backups) |
| RTO | 4 hours (restore into scratch, verify, cut over) |

These are design targets. Record actual restore duration after each drill; do not cite them to the client until a timed restore has passed.

## What is backed up

- Postgres on the `data` Hetzner Cloud server (`kitframe-*-data-1`)
- MinIO object data on the attached Hetzner volume
- Hetzner Cloud server snapshots for the data node (and optionally API/AI/web for faster rebuild)

## Daily procedure (Postgres)

1. On the data host, run a logical dump to the attached volume:

```bash
export TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
pg_dump "$DATABASE_URL" -Fc -f "/mnt/data/backups/postgres/kitframe-${TIMESTAMP}.dump"
find /mnt/data/backups/postgres -type f -mtime +30 -delete
```

2. Sync MinIO bucket inventory (or rely on volume snapshot for block-level consistency):

```bash
mc mirror --overwrite local/kitframe-assets "/mnt/data/backups/minio/${TIMESTAMP}/"
find /mnt/data/backups/minio -mindepth 1 -maxdepth 1 -mtime +30 -exec rm -rf {} +
```

3. Create a Hetzner Cloud snapshot of the data server (and its volume if using separate volume snapshots via the Hetzner API/CLI):

```bash
hcloud server create-image --type snapshot --description "kitframe-data-${TIMESTAMP}" <data-server-id>
```

Retain snapshots for 30 days. Delete older snapshots on a schedule.

## Restore drill (scratch environment)

Time this end to end; stop the clock when health checks and a sample board query succeed.

1. Provision a scratch data server from the latest snapshot (or attach a restored volume).
2. Restore Postgres:

```bash
createdb kitframe_restore
pg_restore --clean --if-exists -d "$RESTORE_DATABASE_URL" /mnt/data/backups/postgres/kitframe-LATEST.dump
```

3. Point MinIO (or restore object tree) and verify a known asset key is readable.
4. Point a scratch API instance at the restored DB and run:

```bash
curl -fsS "$API_URL/healthz"
curl -fsS -H "Authorization: Bearer $TOKEN" "$API_URL/board?limit=20"
```

5. Record wall-clock RTO in the incident log. Target is ≤ 4 hours.

## Production cutover after restore

1. Freeze writes on the failed primary (firewall / stop API and worker).
2. Promote restored data host; update private DNS or terraform outputs consumers.
3. Rolling restart API (2), AI (2), worker (1), web (1).
4. Smoke test login, board, asset download, and one read-only Shopify sync status.
5. Open a post-incident review within 24 hours.

## Validation checklist

- [ ] Latest dump age ≤ 24 hours (RPO)
- [ ] Scratch restore completed ≤ 4 hours (RTO)
- [ ] Row counts for `products`, `assets`, `jobs` match expectations within tolerance
- [ ] Sample assets load from MinIO
- [ ] Snapshot list shows 30-day retention window
