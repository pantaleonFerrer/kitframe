from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image


def delta_e2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 simplified implementation sufficient for QC scoring."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    dL = L2 - L1
    C1 = (a1**2 + b1**2) ** 0.5
    C2 = (a2**2 + b2**2) ** 0.5
    dC = C2 - C1
    da = a2 - a1
    db = b2 - b1
    dH2 = max(da**2 + db**2 - dC**2, 0.0)
    dH = dH2**0.5
    return float((dL**2 + dC**2 + dH**2) ** 0.5)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float64) / 255.0
    mask = rgb > 0.04045
    rgb = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = rgb @ m.T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    eps = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def cluster_colors(image: Image.Image, k: int = 3) -> list[dict[str, Any]]:
    arr = np.array(image.convert("RGB"))
    lab = rgb_to_lab(arr).reshape(-1, 3)
    # Exclude very dark/bright
    mask = (lab[:, 0] >= 5) & (lab[:, 0] <= 95)
    lab = lab[mask]
    if len(lab) == 0:
        return [{"lab": [50.0, 0.0, 0.0], "weight": 1.0}]
    # Simple k-means
    centroids = lab[np.random.choice(len(lab), size=min(k, len(lab)), replace=False)]
    for _ in range(8):
        dists = ((lab[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = dists.argmin(axis=1)
        for i in range(len(centroids)):
            pts = lab[labels == i]
            if len(pts):
                centroids[i] = pts.mean(axis=0)
    weights = []
    for i in range(len(centroids)):
        w = float((labels == i).sum()) / len(lab)
        weights.append({"lab": [float(x) for x in centroids[i]], "weight": w})
    return weights


def score_color(
    candidate: Image.Image,
    reference_colors: list[dict[str, Any]],
    *,
    pass_max: float,
    review_max: float,
) -> dict[str, Any]:
    cand = cluster_colors(candidate, k=len(reference_colors) or 3)
    # Greedy match
    used = set()
    total = 0.0
    weight_sum = 0.0
    for ref in reference_colors:
        best_i, best_d = None, 1e9
        for i, c in enumerate(cand):
            if i in used:
                continue
            d = delta_e2000(tuple(ref["lab"]), tuple(c["lab"]))  # type: ignore[arg-type]
            if d < best_d:
                best_d, best_i = d, i
        if best_i is None:
            continue
        used.add(best_i)
        w = float(ref.get("weight", 1.0))
        total += best_d * w
        weight_sum += w
    score = total / weight_sum if weight_sum else 99.0
    if score <= pass_max:
        result = "pass"
    elif score <= review_max:
        result = "needs_review"
    else:
        result = "fail"
    return {"result": result, "delta_e": score, "clusters": cand}
