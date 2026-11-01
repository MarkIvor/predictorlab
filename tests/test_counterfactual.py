import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

from app.core.business.counterfactual import find_counterfactual


def make_bundle(seed: int = 5, n: int = 1500) -> tuple:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        "risk": rng.normal(0, 1, n).round(3),
        "noise": rng.normal(0, 1, n).round(3),
    })
    y = (rng.random(n) < 1 / (1 + np.exp(-(2.5 * X["risk"])))).astype(int)
    model = CatBoostClassifier(iterations=120, depth=3, verbose=False, random_seed=seed)
    model.fit(X, y)
    feature_cols = ["risk", "noise"]
    bundle = {
        "pipeline": {"kind": "catboost", "estimator": model, "task_type": "binary",
                     "classes": ["0", "1"], "calibrator": None,
                     "spec": {"numeric": feature_cols, "boolean": [], "datetime": {},
                              "categorical": [], "text": [], "feature_cols": feature_cols,
                              "target_col": "y"}},
        "schema": {"input_schema": {"properties": {c: {"type": "number"} for c in feature_cols}}},
        "conformal": {"alpha": 0.9, "q": 0.1},
        "ood": {"threshold": -1.0},
        "metrics": {},
    }
    return bundle, X


def test_cf_respects_bounds_and_immutable():
    bundle, _ = make_bundle()
    record = {"risk": 2.5, "noise": 0.1}
    actionable = {
        "risk": {"min": -2.0, "max": 1.0, "direction": "both", "cost_per_unit": 100},
        "noise": {"immutable": True},
    }
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below",
                             timeout=10.0, cost_matrix=None)
    assert cf is not None and not cf.get("already_ok")
    assert cf["changes"].get("noise") is None, "immutable-признак изменён"
    new_risk = cf["changes"].get("risk")
    assert new_risk is not None and -2.0 - 1e-6 <= new_risk <= 1.0 + 1e-6, "выход за границы"
    assert cf["probability_after"] < 0.5


def test_cf_cost_is_delta_times_unit_cost():
    bundle, _ = make_bundle()
    record = {"risk": 2.0, "noise": 0.0}
    actionable = {"risk": {"min": -2.0, "max": 2.0, "direction": "down", "cost_per_unit": 250}}
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below",
                             timeout=10.0, cost_matrix=None)
    if cf and not cf.get("already_ok"):
        expected = abs(float(cf["changes"]["risk"]) - 2.0) * 250
        assert abs(cf["cost_rub"] - expected) < 1e-6


def test_cf_direction_up_only():
    bundle, _ = make_bundle()
    record = {"risk": -2.5, "noise": 0.0}
    actionable = {"risk": {"min": -3.0, "max": 3.0, "direction": "up", "cost_per_unit": 10}}
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="above",
                             timeout=10.0, cost_matrix=None)
    if cf and not cf.get("already_ok"):
        assert float(cf["changes"]["risk"]) >= -2.5, "direction=up не должен уменьшать признак"
        assert cf["probability_after"] >= 0.5


def test_cf_honest_not_found():
    bundle, _ = make_bundle()
    record = {"risk": 2.5, "noise": 0.1}
    actionable = {"risk": {"min": 2.4, "max": 2.6, "direction": "both", "cost_per_unit": 1}}
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below",
                             timeout=2.0, cost_matrix=None)
    assert cf is None, "в узких рамках действия нет — честный ответ"


def test_cf_property_bounds_repeated():
    rng = np.random.default_rng(33)
    bundle, _ = make_bundle(seed=9)
    for _ in range(25):
        record = {"risk": round(float(rng.normal(0, 2)), 2), "noise": round(float(rng.normal(0, 1)), 2)}
        actionable = {"risk": {"min": -1.5, "max": 1.5, "direction": "both", "cost_per_unit": 10},
                      "noise": {"immutable": True}}
        cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below",
                                 timeout=3.0, cost_matrix=None)
        if cf and not cf.get("already_ok"):
            new_risk = float(cf["changes"].get("risk", record["risk"]))
            assert -1.5 - 1e-6 <= new_risk <= 1.5 + 1e-6
            assert "noise" not in cf["changes"]
