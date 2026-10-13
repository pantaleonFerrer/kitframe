from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PIL import Image


def check_crest(
    candidate: Image.Image,
    template: Image.Image | None,
    *,
    pass_min: float,
    review_min: float,
    position_tolerance: float,
    check_position: bool,
) -> dict[str, Any]:
    if template is None:
        return {"result": "pass", "confidence": 1.0, "detected_box": None, "reason": "no_template"}
    cand = cv2.cvtColor(np.array(candidate.convert("RGB")), cv2.COLOR_RGB2GRAY)
    tmpl = cv2.cvtColor(np.array(template.convert("RGB")), cv2.COLOR_RGB2GRAY)
    # Template matching fallback (works without heavy SIFT dependency issues)
    best = 0.0
    best_box = None
    th, tw = tmpl.shape[:2]
    ch, cw = cand.shape[:2]
    for scale in np.linspace(0.5, 2.0, 16):
        nw, nh = int(tw * scale), int(th * scale)
        if nw < 8 or nh < 8 or nw >= cw or nh >= ch:
            continue
        resized = cv2.resize(tmpl, (nw, nh))
        res = cv2.matchTemplate(cand, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best:
            best = float(max_val)
            x, y = max_loc
            best_box = {
                "x": x / cw,
                "y": y / ch,
                "w": nw / cw,
                "h": nh / ch,
            }
    confidence = max(0.0, min(1.0, best))
    position_ok = True
    if check_position and best_box is not None:
        # Expected roughly center-left for jersey crest; use template center ratio if available
        cx = best_box["x"] + best_box["w"] / 2
        cy = best_box["y"] + best_box["h"] / 2
        # Soft check around typical crest area
        position_ok = abs(cx - 0.5) <= 0.35 + position_tolerance and abs(cy - 0.35) <= 0.35 + position_tolerance
    if confidence >= pass_min and (position_ok or not check_position):
        result = "pass"
    elif confidence >= review_min:
        result = "needs_review"
    else:
        result = "fail"
    return {"result": result, "confidence": confidence, "detected_box": best_box, "position_ok": position_ok}
