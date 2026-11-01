import numpy as np
import pandas as pd
import pytest
from app.core.business.profit import compute_threshold, profit_at
from hypothesis import given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property


def _make_holdout(y: np.ndarray, proba: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"y_true": y, "proba": proba})


@settings(max_examples=50, deadline=None)
@given(
    benefit=st.floats(min_value=100, max_value=100000),
    action=st.floats(min_value=10, max_value=1000),
    fn_cost=st.floats(min_value=0, max_value=50000),
    seed=st.integers(min_value=0, max_value=10000),
)
def test_profit_monotone_in_benefit(benefit: float, action: float, fn_cost: float, seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 500
    y = (rng.random(n) < 0.3).astype(int)
    proba = np.sort(rng.beta(2, 5, n))
    ho = _make_holdout(y, proba)
    p1 = compute_threshold(ho, {"benefit_tp": benefit, "action_cost": action, "fn_cost": fn_cost})
    p2 = compute_threshold(ho, {"benefit_tp": benefit * 1.5, "action_cost": action, "fn_cost": fn_cost})
    assert p2["profit"] >= p1["profit"] - 0.01


@settings(max_examples=50, deadline=None)
@given(
    tp=st.integers(min_value=0, max_value=500),
    fp=st.integers(min_value=0, max_value=500),
    fn=st.integers(min_value=0, max_value=500),
    benefit=st.floats(min_value=0, max_value=100000),
    action=st.floats(min_value=0, max_value=1000),
    fn_cost=st.floats(min_value=0, max_value=50000),
)
def test_profit_formula_always_matches_manual(tp: int, fp: int, fn: int, benefit: float, action: float, fn_cost: float) -> None:
    manual = tp * (benefit - action) - fp * action - fn * fn_cost
    computed = profit_at(tp, fp, fn, {"benefit_tp": benefit, "action_cost": action, "fn_cost": fn_cost})
    assert abs(manual - computed) < 0.01


@settings(max_examples=50, deadline=None)
@given(seed=st.integers(min_value=0, max_value=100000))
def test_threshold_always_within_probability_range(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 500
    y = (rng.random(n) < 0.3).astype(int)
    proba = np.sort(rng.beta(2, 5, n))
    ho = _make_holdout(y, proba)
    info = compute_threshold(ho, {"benefit_tp": 50000, "action_cost": 1000, "fn_cost": 5000})
    assert info["threshold"] <= 1.0
    assert info["threshold"] >= 0.0
