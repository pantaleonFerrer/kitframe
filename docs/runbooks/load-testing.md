# Load testing

## Targets (BUILD_SPEC Section 20)

| Operation | Target |
|---|---|
| Board page load (100 products) | < 1.5s p95 |
| Asset search (embedding query) | < 500ms p95 |

Seed volume for realistic runs: on the order of 10,000 products (plus associated assets).

## Tooling

- k6 script: `scripts/load/board.js`
- Auth: obtain a bearer token for a non-production user before the test
- Base URL: staging API (`BASE_URL`), never production unless explicitly approved

## Board scenario

```bash
export BASE_URL=https://staging.example/v1
export TOKEN=...
k6 run scripts/load/board.js
```

The script exercises authenticated board listing with pagination under sustained VU load. Pass criteria: p95 board latency under 1.5s at the agreed VU level with error rate < 1%.

## Search scenario

Extend or duplicate the board script to call asset search:

```bash
k6 run -e SCENARIO=search scripts/load/board.js
```

Pass criteria: p95 search latency under 500ms with error rate < 1%.

## Practice

1. Reset staging DB from a anonymized large seed (or synthetic 10k products).
2. Warm caches with a short pre-run.
3. Run board and search scenarios separately, then a mixed profile.
4. Capture API, Postgres, and MinIO metrics during the run.
5. If targets miss: check N+1 queries, missing indexes, default page size, and embedding search plans before adding hardware.

## Report template

- Date, SHA, environment
- VUs, duration, seed size
- p50/p95/p99 for board and search
- Error rate and top failing routes
- Follow-up tickets
