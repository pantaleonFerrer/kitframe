from __future__ import annotations

from typing import Any


def check_resolution(
    width: int,
    height: int,
    min_short_side_px: int,
    *,
    origin: str | None = None,
    min_short_side_px_generated: int | None = None,
) -> dict[str, Any]:
    short = min(width, height)
    threshold = min_short_side_px
    if origin == "generated" and min_short_side_px_generated is not None:
        threshold = min_short_side_px_generated
    ok = short >= threshold
    return {
        "result": "pass" if ok else "fail",
        "short_side_px": short,
        "min_short_side_px": threshold,
    }
