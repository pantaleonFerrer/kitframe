from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel

from app.config import Settings, get_settings

QCResult = Literal["pass", "needs_review", "fail"]

COLOR_WEIGHT_KEY = "color"
LOGO_WEIGHT_KEY = "logo"
RESOLUTION_WEIGHT_KEY = "resolution"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class QCScoreRequest(BaseModel):
    asset_url: str
    golden_set_image_id: str
    golden_set_image_url: str
    logo_bounding_box: BoundingBox | None = None
    candidate_image_lab: list[list[float]] | None = None
    golden_image_lab: list[list[float]] | None = None
    candidate_width: int | None = None
    candidate_height: int | None = None
    golden_width: int | None = None
    golden_height: int | None = None
    target_min_width: int = 1000
    target_min_height: int = 1000
    logo_detection_score: float | None = None
    logo_detection_uncertain: bool = False


class QCScoreDetail(BaseModel):
    color: dict[str, Any]
    logo_position: dict[str, Any] | None
    resolution: dict[str, Any]
    weights: dict[str, float]
    logo_near_miss: bool
    logo_uncertain: bool


class QCScoreResponse(BaseModel):
    color_score: float
    logo_position_score: float | None
    resolution_score: float
    overall_score: float
    result: QCResult
    detail: QCScoreDetail
    golden_set_image_id: str


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float64)
    if rgb.ndim == 1:
        rgb = rgb.reshape(1, -1)
    rgb = rgb / 255.0
    mask = rgb > 0.04045
    rgb = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ],
        dtype=np.float64,
    )
    xyz = rgb @ m.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
    epsilon = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    f = np.where(xyz > epsilon, np.cbrt(xyz), (kappa * xyz + 16.0) / 116.0)
    l = 116.0 * f[:, 1] - 16.0
    a = 500.0 * (f[:, 0] - f[:, 1])
    b = 200.0 * (f[:, 1] - f[:, 2])
    return np.stack([l, a, b], axis=1)


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    if lab1.ndim == 1:
        lab1 = lab1.reshape(1, -1)
    if lab2.ndim == 1:
        lab2 = lab2.reshape(1, -1)

    L1, a1, b1 = lab1[:, 0], lab1[:, 1], lab1[:, 2]
    L2, a2, b2 = lab2[:, 0], lab2[:, 1], lab2[:, 2]

    kL = 1.0
    kC = 1.0
    kH = 1.0

    C1 = np.sqrt(a1 * a1 + b1 * b1)
    C2 = np.sqrt(a2 * a2 + b2 * b2)
    C_bar = 0.5 * (C1 + C2)
    C_bar7 = C_bar ** 7
    G = 0.5 * (1.0 - np.sqrt(C_bar7 / (C_bar7 + 25.0 ** 7)))

    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.sqrt(a1p * a1p + b1 * b1)
    C2p = np.sqrt(a2p * a2p + b2 * b2)
    C_bar_p = 0.5 * (C1p + C2p)

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    dhp = np.where((C1p * C2p) == 0.0, 0.0, dhp)
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    L_bar_p = 0.5 * (L1 + L2)
    h_bar_p = h1p + h2p
    h_bar_p = np.where(
        (C1p * C2p) == 0.0,
        h1p + h2p,
        np.where(
            np.abs(h1p - h2p) > 180.0,
            np.where(h_bar_p < 360.0, h_bar_p + 360.0, h_bar_p - 360.0) / 2.0,
            h_bar_p / 2.0,
        ),
    )

    T = (
        1.0
        - 0.17 * np.cos(np.radians(h_bar_p - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_bar_p))
        + 0.32 * np.cos(np.radians(3.0 * h_bar_p + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_bar_p - 63.0))
    )

    d_ro = 30.0 * np.exp(-(((h_bar_p - 275.0) / 25.0) ** 2))
    C_bar_p7 = C_bar_p ** 7
    R_C = 2.0 * np.sqrt(C_bar_p7 / (C_bar_p7 + 25.0 ** 7))
    S_L = 1.0 + (0.015 * (L_bar_p - 50.0) ** 2) / np.sqrt(20.0 + (L_bar_p - 50.0) ** 2)
    S_C = 1.0 + 0.045 * C_bar_p
    S_H = 1.0 + 0.015 * C_bar_p * T
    R_T = -np.sin(np.radians(2.0 * d_ro)) * R_C

    return np.sqrt(
        (dLp / (kL * S_L)) ** 2
        + (dCp / (kC * S_C)) ** 2
        + (dHp / (kH * S_H)) ** 2
        + R_T * (dCp / (kC * S_C)) * (dHp / (kH * S_H))
    )


def normalize_delta_e(
    delta_e: float,
    scale: float,
    exponent: float,
) -> float:
    if scale <= 0.0:
        return 0.0
    value = math.exp(-((max(delta_e, 0.0) / scale) ** exponent))
    return float(max(0.0, min(1.0, value)))


def mean_lab_from_rgb_samples(samples: np.ndarray) -> np.ndarray:
    labs = rgb_to_lab(samples)
    return labs.mean(axis=0)


def color_score_from_lab_means(
    candidate_lab: np.ndarray,
    golden_lab: np.ndarray,
    settings: Settings,
) -> tuple[float, float]:
    de = float(delta_e_2000(candidate_lab, golden_lab)[0])
    score = normalize_delta_e(
        de,
        settings.delta_e_curve_scale,
        settings.delta_e_curve_exponent,
    )
    return score, de


def resolution_score(
    width: int,
    height: int,
    min_width: int,
    min_height: int,
) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    w_ratio = min(1.0, width / float(min_width))
    h_ratio = min(1.0, height / float(min_height))
    return float(min(w_ratio, h_ratio))


def compute_logo_position_score(
    logo_detection_score: float | None,
    logo_detection_uncertain: bool,
    has_bbox: bool,
) -> tuple[float | None, bool]:
    if not has_bbox:
        return None, False
    if logo_detection_uncertain or logo_detection_score is None:
        return None, True
    return float(max(0.0, min(1.0, logo_detection_score))), False


def weighted_overall(
    color: float,
    logo: float | None,
    resolution: float,
    settings: Settings,
) -> tuple[float, dict[str, float]]:
    if logo is None:
        total = settings.color_weight + settings.resolution_weight
        weights = {
            COLOR_WEIGHT_KEY: settings.color_weight / total,
            RESOLUTION_WEIGHT_KEY: settings.resolution_weight / total,
        }
        overall = weights[COLOR_WEIGHT_KEY] * color + weights[RESOLUTION_WEIGHT_KEY] * resolution
        return float(overall), weights

    weights = {
        COLOR_WEIGHT_KEY: settings.color_weight,
        LOGO_WEIGHT_KEY: settings.logo_weight,
        RESOLUTION_WEIGHT_KEY: settings.resolution_weight,
    }
    overall = (
        weights[COLOR_WEIGHT_KEY] * color
        + weights[LOGO_WEIGHT_KEY] * logo
        + weights[RESOLUTION_WEIGHT_KEY] * resolution
    )
    return float(overall), weights


def decide_result(
    overall: float,
    checks: list[float],
    logo_near_miss: bool,
    logo_uncertain: bool,
    settings: Settings,
) -> QCResult:
    if logo_uncertain or logo_near_miss:
        if overall < settings.qc_fail_threshold:
            return "fail"
        return "needs_review"
    if overall < settings.qc_fail_threshold:
        return "fail"
    if overall >= settings.qc_pass_threshold and all(c >= settings.qc_check_floor for c in checks):
        return "pass"
    return "needs_review"


def score_qc(request: QCScoreRequest, settings: Settings | None = None) -> QCScoreResponse:
    settings = settings or get_settings()

    if request.candidate_image_lab is not None and request.golden_image_lab is not None:
        candidate_lab = np.asarray(request.candidate_image_lab, dtype=np.float64).mean(axis=0)
        golden_lab = np.asarray(request.golden_image_lab, dtype=np.float64).mean(axis=0)
    else:
        candidate_lab = np.array([50.0, 0.0, 0.0], dtype=np.float64)
        golden_lab = np.array([50.0, 0.0, 0.0], dtype=np.float64)

    color, delta_e = color_score_from_lab_means(candidate_lab, golden_lab, settings)

    logo, logo_uncertain = compute_logo_position_score(
        request.logo_detection_score,
        request.logo_detection_uncertain,
        request.logo_bounding_box is not None,
    )

    width = request.candidate_width or request.target_min_width
    height = request.candidate_height or request.target_min_height
    res = resolution_score(width, height, request.target_min_width, request.target_min_height)

    overall, weights = weighted_overall(color, logo, res, settings)

    logo_near_miss = False
    if logo is not None and not logo_uncertain:
        logo_near_miss = logo < settings.qc_pass_threshold

    checks = [color, res]
    if logo is not None:
        checks.append(logo)

    result = decide_result(overall, checks, logo_near_miss, logo_uncertain, settings)

    detail = QCScoreDetail(
        color={
            "score": color,
            "delta_e_2000": delta_e,
            "curve_scale": settings.delta_e_curve_scale,
            "curve_exponent": settings.delta_e_curve_exponent,
        },
        logo_position=(
            None
            if request.logo_bounding_box is None
            else {
                "score": logo,
                "uncertain": logo_uncertain,
                "near_miss": logo_near_miss,
                "bounding_box": request.logo_bounding_box.model_dump(),
            }
        ),
        resolution={
            "score": res,
            "width": width,
            "height": height,
            "target_min_width": request.target_min_width,
            "target_min_height": request.target_min_height,
        },
        weights=weights,
        logo_near_miss=logo_near_miss,
        logo_uncertain=logo_uncertain,
    )

    return QCScoreResponse(
        color_score=color,
        logo_position_score=logo,
        resolution_score=res,
        overall_score=overall,
        result=result,
        detail=detail,
        golden_set_image_id=request.golden_set_image_id,
    )
