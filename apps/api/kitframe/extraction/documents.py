from __future__ import annotations

"""Document conversion helpers for extraction (§8.2)."""

from pathlib import Path


def detect_file_type(file_name: str) -> str:
    ext = Path(file_name).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".xlsx", ".xls"}:
        return "xlsx"
    return "image"
