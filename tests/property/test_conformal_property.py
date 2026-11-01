import numpy as np
import pytest
from app.core.uncertainty.conformal import calibrate_regression, regression_interval
from hypothesis import given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property


@settings(max_examples=30, deadline=None)
@given(
    alpha=st.floats(min_value=0.5, max_value=0.99),
    noise=st.floats(min_value=0.1, max_value=5.0),
    seed=st.integers(min_value=0, max_value=10000),
)
def test_regression_interval_coverage_increasing_with_alpha(alpha: float, noise: float, seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 2000
    pred = rng.normal(0, 1, n)
    y = pred + rng.normal(0, noise, n)
    conformal = calibrate_regression(pred, y, alpha=alpha)
    lo, hi = regression_interval(0.0, conformal)
    width = hi - lo
    conformal_lower = calibrate_regression(pred, y, alpha=max(0.5, alpha - 0.1))
    lo2, hi2 = regression_interval(0.0, conformal_lower)
    width_lower = hi2 - lo2
    assert width >= width_lower, "интервал должен быть шире при большем α"
    assert lo <= hi
    assert conformal["q"] >= 0


@settings(max_examples=30, deadline=None)
@given(seed=st.integers(min_value=0, max_value=100000))
def test_interval_is_symmetric_around_prediction(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 2000
    pred = rng.normal(0, 1, n)
    y = pred + rng.normal(0, 1, n)
    conformal = calibrate_regression(pred, y, alpha=0.9)
    lo, hi = regression_interval(5.0, conformal)
    mid = (lo + hi) / 2
    assert abs(mid - 5.0) < 1e-10
