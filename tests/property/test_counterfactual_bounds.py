import numpy as np
import pandas as pd
import pytest
from app.core.business.counterfactual import find_counterfactual
from catboost import CatBoostClassifier
from hypothesis import given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property


def make_bundle_and_record(seed: int = 5, risk_val: float = 2.0) -> tuple[dict, dict]:
    rng = np.random.default_rng(seed)
    n = 1500
    X = pd.DataFrame(
        {
            "risk": rng.normal(0, 1, n).round(3),
            "noise": rng.normal(0, 1, n).round(3),
        }
    )
    y = (rng.random(n) < 1 / (1 + np.exp(-(2.5 * X["risk"])))).astype(int)
    model = CatBoostClassifier(iterations=120, depth=3, verbose=False, random_seed=seed)
    model.fit(X, y)
    bundle = {
        "pipeline": {
            "kind": "catboost",
            "estimator": model,
            "task_type": "binary",
            "classes": ["0", "1"],
            "calibrator": None,
            "spec": {
                "numeric": ["risk", "noise"],
                "boolean": [],
                "datetime": {},
                "categorical": [],
                "text": [],
                "feature_cols": ["risk", "noise"],
                "target_col": "y",
            },
        },
        "schema": {"input_schema": {"properties": {"risk": {"type": "number"}, "noise": {"type": "number"}}}},
        "conformal": {"alpha": 0.9, "q": 0.1},
        "ood": {"threshold": -1.0},
        "metrics": {},
    }
    record = {"risk": risk_val, "noise": 0.1}
    return bundle, record


@settings(max_examples=20, deadline=None)
@given(
    min_bound=st.floats(min_value=-3.0, max_value=0.0),
    max_bound=st.floats(min_value=0.5, max_value=3.0),
    risk_val=st.floats(min_value=0.5, max_value=3.0),
    cost=st.floats(min_value=1, max_value=1000),
)
def test_cf_never_exceeds_bounds(min_bound: float, max_bound: float, risk_val: float, cost: float) -> None:
    if min_bound >= max_bound:
        return
    bundle, record = make_bundle_and_record(risk_val=risk_val)
    actionable = {"risk": {"min": min_bound, "max": max_bound, "direction": "both", "cost_per_unit": cost}}
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below", timeout=3.0, cost_matrix=None)
    if cf and not cf.get("already_ok"):
        new_val = cf["changes"].get("risk")
        if new_val is not None:
            assert min_bound - 1e-6 <= new_val <= max_bound + 1e-6, f"выход за границы: {new_val} not in [{min_bound}, {max_bound}]"


@settings(max_examples=20, deadline=None)
@given(
    risk_val=st.floats(min_value=0.5, max_value=3.0),
    cost=st.floats(min_value=1, max_value=500),
)
def test_cf_immutable_never_changed(risk_val: float, cost: float) -> None:
    bundle, record = make_bundle_and_record(risk_val=risk_val)
    actionable = {
        "risk": {"min": -2.0, "max": 2.0, "direction": "both", "cost_per_unit": cost},
        "noise": {"immutable": True},
    }
    cf = find_counterfactual(bundle, record, actionable, threshold=0.5, direction="below", timeout=3.0, cost_matrix=None)
    if cf and not cf.get("already_ok"):
        assert "noise" not in cf["changes"], "immutable-признак был изменён!"
