"""Upload seed fixture JPEGs to object storage (S3 / MinIO)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from kitframe.media.storage import ensure_bucket, key_prefix, put_bytes
from kitframe.settings import Settings, get_settings

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

POSE_NAMES = ("Frontal brazos relajados", "Perfil caminando", "Tres cuartos")
STYLE_NAMES = ("Estudio gris", "Luz suave", "Editorial")
PRODUCT_REFS = tuple(f"FCB-DEMO-{i:03d}" for i in range(1, 7))
SHOTS = ("product_front", "product_back", "product_detail")
# Definitive product gallery shots used in review / publish demos
PRODUCT_FINAL_SHOTS = ("product_front", "product_back", "model_front")


def seed_media_map() -> dict[str, str]:
    """local relative path under fixtures/ → storage_key in bucket."""
    mapping: dict[str, str] = {}
    for ref in PRODUCT_REFS:
        for shot in SHOTS:
            rel = f"garment/{ref}/{shot}.jpg"
            mapping[rel] = f"seed/{rel}"
    for i in range(1, 6):
        mapping[f"model/{i}.jpg"] = f"seed/model/{i}.jpg"
    for name in POSE_NAMES:
        mapping[f"pose/{name}.jpg"] = f"seed/pose/{name}.jpg"
    for name in STYLE_NAMES:
        mapping[f"style/{name}.jpg"] = f"seed/style/{name}.jpg"
    mapping["golden/jersey-front.jpg"] = "seed/golden/jersey-front.jpg"
    return mapping


SEED_MEDIA_MAP = seed_media_map()


def _fixture_bytes(rel: str) -> bytes:
    path = FIXTURES_DIR / rel
    if not path.is_file():
        raise FileNotFoundError(f"Missing seed fixture: {rel}")
    return path.read_bytes()


def upload_seed_media(settings: Settings | None = None) -> int:
    """Put all seed fixtures into the configured bucket. Returns count uploaded."""
    settings = settings or get_settings()
    ensure_bucket(settings)
    uploaded = 0
    missing: list[str] = []
    for rel, key in seed_media_map().items():
        path = FIXTURES_DIR / rel
        if not path.is_file():
            missing.append(rel)
            continue
        put_bytes(settings, key, path.read_bytes(), "image/jpeg")
        uploaded += 1

    # Definitive product images: reuse garment/model fixtures under seed/product/…
    for ref in PRODUCT_REFS:
        for shot in PRODUCT_FINAL_SHOTS:
            if shot == "model_front":
                src = "model/1.jpg"
            else:
                src = f"garment/{ref}/{shot}.jpg"
            key = f"seed/product/{ref}/{shot}.jpg"
            put_bytes(settings, key, _fixture_bytes(src), "image/jpeg")
            uploaded += 1

    if missing:
        raise FileNotFoundError(
            f"Missing seed fixtures ({len(missing)}): {', '.join(missing[:8])}"
        )
    print(
        f"Seed media uploaded: {uploaded} objects → "
        f"s3://{settings.s3_bucket}/{key_prefix(settings)}/seed/…"
    )
    return uploaded


def sha256_file(rel: str) -> str:
    path = FIXTURES_DIR / rel
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_product_final(ref: str, shot: str) -> str:
    if shot == "model_front":
        return sha256_file("model/1.jpg")
    return sha256_file(f"garment/{ref}/{shot}.jpg")
