#!/usr/bin/env bash
# Set S3 CORS so browser uploads from localhost work (AWS mode).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/api"
# shellcheck disable=SC1091
source .venv/bin/activate
cd "$ROOT"
python3 <<'PY'
from kitframe.settings import get_settings
from kitframe.media.storage import s3_client

settings = get_settings()
client = s3_client(settings)
cors = {
    "CORSRules": [
        {
            "AllowedOrigins": [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
            "AllowedMethods": ["GET", "PUT", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag", "x-amz-request-id"],
            "MaxAgeSeconds": 3000,
        }
    ]
}
client.put_bucket_cors(Bucket=settings.s3_bucket, CORSConfiguration=cors)
print(f"CORS OK on s3://{settings.s3_bucket} for localhost:3000")
print(client.get_bucket_cors(Bucket=settings.s3_bucket))
PY
