from __future__ import annotations

from kitframe.media.storage import build_storage_key, resolve_storage_key
from kitframe.settings import Settings


def test_resolve_storage_key_prefixes() -> None:
    s = Settings(s3_key_prefix="kitframe")
    assert resolve_storage_key(s, "brands/abc/x.jpg") == "kitframe/brands/abc/x.jpg"
    assert resolve_storage_key(s, "kitframe/brands/abc/x.jpg") == "kitframe/brands/abc/x.jpg"
    assert resolve_storage_key(s, "/seed/foo.jpg") == "kitframe/seed/foo.jpg"


def test_build_storage_key() -> None:
    s = Settings(s3_key_prefix="kitframe")
    assert build_storage_key(s, "brands", "b1", "asset", "f.png") == "kitframe/brands/b1/asset/f.png"
