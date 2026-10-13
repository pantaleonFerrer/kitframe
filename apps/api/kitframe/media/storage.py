from __future__ import annotations

from typing import Any
from uuid import uuid4

import boto3
from botocore.client import Config

from kitframe.settings import Settings


def _client(settings: Settings) -> Any:
    kwargs: dict[str, Any] = {
        "aws_access_key_id": settings.s3_access_key_id,
        "aws_secret_access_key": settings.s3_secret_access_key,
        "region_name": settings.s3_region,
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_use_path_style else "virtual"},
        ),
    }
    if settings.s3_endpoint:
        kwargs["endpoint_url"] = settings.s3_endpoint
    return boto3.client("s3", **kwargs)


def storage_reachable(settings: Settings) -> bool:
    try:
        client = _client(settings)
        client.head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False


def presign_put(
    settings: Settings,
    *,
    brand_id: str,
    kind: str,
    file_name: str,
    content_type: str,
    max_size: int,
) -> dict[str, str]:
    key = f"brands/{brand_id}/{kind}/{uuid4()}/{file_name}"
    client = _client(settings)
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=600,
    )
    return {"storage_key": key, "upload_url": url, "max_size": str(max_size)}


def presign_get(settings: Settings, storage_key: str, expires: int = 900) -> str:
    client = _client(settings)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": storage_key},
        ExpiresIn=expires,
    )


def put_bytes(settings: Settings, storage_key: str, content: bytes, content_type: str) -> None:
    client = _client(settings)
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=storage_key,
        Body=content,
        ContentType=content_type,
    )


def get_bytes(settings: Settings, storage_key: str) -> bytes:
    client = _client(settings)
    obj = client.get_object(Bucket=settings.s3_bucket, Key=storage_key)
    return obj["Body"].read()


def ensure_bucket(settings: Settings) -> None:
    client = _client(settings)
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        if settings.uses_aws_s3:
            # Do not auto-create remote AWS buckets; they must already exist.
            raise
        client.create_bucket(Bucket=settings.s3_bucket)
