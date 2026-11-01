import numpy as np
from app.core.uncertainty.conformal import (
    calibrate_classification,
    calibrate_regression,
    predict_set,
    regression_interval,
)


def test_regression_coverage_within_5pp():
    rng = np.random.default_rng(11)
    n_calib, n_test = 3000, 3000
    pred_cal = rng.normal(0, 1, n_calib)
    y_cal = pred_cal + rng.normal(0, 2, n_calib)
    conformal = calibrate_regression(pred_cal, y_cal, alpha=0.9)
    pred_test = rng.normal(0, 1, n_test)
    y_test = pred_test + rng.normal(0, 2, n_test)
    covered = 0
    for p, y in zip(pred_test, y_test, strict=False):
        lo, hi = regression_interval(p, conformal)
        covered += lo <= y <= hi
    coverage = covered / n_test
    assert 0.85 <= coverage <= 0.95, f"покрытие {coverage}"


def test_classification_aps_coverage_one_sided():
    rng = np.random.default_rng(12)
    n_calib, n_test = 4000, 4000
    y_cal = rng.integers(0, 2, n_calib)
    proba_cal = np.clip(0.3 + 0.4 * y_cal + rng.normal(0, 0.15, n_calib), 0.01, 0.99)
    probs_cal = np.column_stack([1 - proba_cal, proba_cal])
    conformal = calibrate_classification(probs_cal, y_cal, alpha=0.9)
    y_test = rng.integers(0, 2, n_test)
    proba_test = np.clip(0.3 + 0.4 * y_test + rng.normal(0, 0.15, n_test), 0.01, 0.99)
    covered = 0
    for p, y in zip(proba_test, y_test, strict=False):
        s = predict_set(np.array([1 - p, p]), conformal, ["0", "1"])
        covered += str(int(y)) in s
    coverage = covered / n_test
    assert coverage >= 0.88, f"покрытие {coverage} (односторонняя гарантия ≥ α)"


def test_sets_shrink_when_confident():
    conformal = {"q": 0.2}
    s = predict_set(np.array([0.95, 0.05]), conformal, ["0", "1"])
    assert s == ["0"]
    s2 = predict_set(np.array([0.55, 0.45]), conformal, ["0", "1"])
    assert s2 == ["0", "1"]
