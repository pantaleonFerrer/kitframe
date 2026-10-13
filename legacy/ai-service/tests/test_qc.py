from app.config import Settings
from app.qc import (
    BoundingBox,
    QCScoreRequest,
    color_score_from_lab_means,
    decide_result,
    delta_e_2000,
    normalize_delta_e,
    rgb_to_lab,
    score_qc,
    weighted_overall,
)
import numpy as np


def test_delta_e_identical_is_zero():
    lab = np.array([[50.0, 10.0, -5.0]])
    assert float(delta_e_2000(lab, lab)[0]) < 1e-6


def test_delta_e_known_difference_positive():
    lab1 = np.array([[50.0, 2.6772, -79.7751]])
    lab2 = np.array([[50.0, 0.0, -82.7485]])
    de = float(delta_e_2000(lab1, lab2)[0])
    assert 1.0 < de < 5.0


def test_normalize_delta_e_curve_uses_named_constants():
    scale = 20.0
    exponent = 1.0
    assert normalize_delta_e(0.0, scale, exponent) == 1.0
    mid = normalize_delta_e(scale, scale, exponent)
    assert abs(mid - np.exp(-1.0)) < 1e-9
    assert normalize_delta_e(1000.0, scale, exponent) < 0.01


def test_rgb_to_lab_round_trip_shape():
    rgb = np.array([[255.0, 0.0, 0.0], [0.0, 255.0, 0.0]])
    lab = rgb_to_lab(rgb)
    assert lab.shape == (2, 3)


def test_color_score_identical_images():
    settings = Settings(delta_e_curve_scale=20.0, delta_e_curve_exponent=1.0)
    lab = np.array([50.0, 0.0, 0.0])
    score, de = color_score_from_lab_means(lab, lab, settings)
    assert de == 0.0
    assert score == 1.0


def test_pass_requires_threshold_and_floor():
    settings = Settings(
        qc_pass_threshold=0.90,
        qc_fail_threshold=0.60,
        qc_check_floor=0.75,
    )
    assert decide_result(0.95, [0.95, 0.95, 0.95], False, False, settings) == "pass"
    assert decide_result(0.95, [0.95, 0.70, 0.95], False, False, settings) == "needs_review"
    assert decide_result(0.55, [0.55, 0.55], False, False, settings) == "fail"
    assert decide_result(0.85, [0.85, 0.85], False, False, settings) == "needs_review"


def test_logo_near_miss_forces_needs_review():
    settings = Settings(
        qc_pass_threshold=0.90,
        qc_fail_threshold=0.60,
        qc_check_floor=0.75,
        color_weight=0.5,
        logo_weight=0.3,
        resolution_weight=0.2,
        delta_e_curve_scale=20.0,
        delta_e_curve_exponent=1.0,
    )
    request = QCScoreRequest(
        asset_url="mock://candidate",
        golden_set_image_id="gs-1",
        golden_set_image_url="mock://golden",
        logo_bounding_box=BoundingBox(x=10, y=10, width=40, height=40),
        candidate_image_lab=[[50.0, 0.0, 0.0]],
        golden_image_lab=[[50.0, 0.0, 0.0]],
        candidate_width=2000,
        candidate_height=2000,
        logo_detection_score=0.82,
        logo_detection_uncertain=False,
    )
    result = score_qc(request, settings)
    assert result.overall_score >= settings.qc_pass_threshold
    assert result.result == "needs_review"
    assert result.detail.logo_near_miss is True


def test_logo_uncertain_forces_needs_review():
    settings = Settings(
        qc_pass_threshold=0.90,
        qc_fail_threshold=0.60,
        qc_check_floor=0.75,
        delta_e_curve_scale=20.0,
        delta_e_curve_exponent=1.0,
    )
    request = QCScoreRequest(
        asset_url="mock://candidate",
        golden_set_image_id="gs-2",
        golden_set_image_url="mock://golden",
        logo_bounding_box=BoundingBox(x=10, y=10, width=40, height=40),
        candidate_image_lab=[[50.0, 0.0, 0.0]],
        golden_image_lab=[[50.0, 0.0, 0.0]],
        candidate_width=2000,
        candidate_height=2000,
        logo_detection_score=None,
        logo_detection_uncertain=True,
    )
    result = score_qc(request, settings)
    assert result.logo_position_score is None
    assert result.result == "needs_review"
    assert result.detail.logo_uncertain is True


def test_overall_weights_color_highest():
    settings = Settings(color_weight=0.5, logo_weight=0.3, resolution_weight=0.2)
    overall, weights = weighted_overall(1.0, 0.0, 0.0, settings)
    assert weights["color"] == 0.5
    assert abs(overall - 0.5) < 1e-9
