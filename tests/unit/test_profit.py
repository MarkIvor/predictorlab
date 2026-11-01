import numpy as np
import pandas as pd
from app.core.business.profit import compute_threshold, profit_at, regression_cost


def holdout_frame(seed: int = 5, n: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    proba = np.sort(rng.beta(2, 6, n))
    y = (rng.random(n) < proba * 0.8 + 0.05).astype(int)
    return pd.DataFrame({"y_true": y, "proba": proba})


def test_profit_matches_manual_calc():
    ho = holdout_frame()
    cost = {"benefit_tp": 40000, "action_cost": 1500, "fn_cost": 8000}
    info = compute_threshold(ho, cost)
    t = info["threshold"]
    y = ho["y_true"].to_numpy()
    p = ho["proba"].to_numpy()
    treated = p >= t
    tp = int(np.sum(treated & (y == 1)))
    fp = int(np.sum(treated & (y == 0)))
    fn = int(np.sum(~treated & (y == 1)))
    manual = profit_at(tp, fp, fn, cost)
    assert abs(manual - info["profit"]) < 0.01


def test_threshold_is_profit_maximum():
    ho = holdout_frame()
    info = compute_threshold(ho, {"benefit_tp": 40000, "action_cost": 1500, "fn_cost": 8000})
    curve = info["curve"]
    best_curve = max(pt["profit"] for pt in curve)
    assert info["profit"] >= best_curve - 0.01


def test_threshold_differs_from_half_on_asymmetric_costs():
    ho = holdout_frame()
    info = compute_threshold(ho, {"benefit_tp": 40000, "action_cost": 100, "fn_cost": 30000})
    assert abs(info["threshold"] - 0.5) > 0.01
    assert info["threshold"] < 0.5, "при дорогом пропуске порог должен снижаться"
    cheap = compute_threshold(ho, {"benefit_tp": 10, "action_cost": 10000, "fn_cost": 0})
    assert cheap["tp"] + cheap["fp"] <= 1, "при запретительной цене действия обрабатывается почти никто"


def test_capacity_limits_treated():
    ho = holdout_frame()
    info = compute_threshold(ho, {"benefit_tp": 50000, "action_cost": 10, "fn_cost": 5000, "capacity": 50})
    assert info["n_treated"] <= 50
    assert info["tp"] + info["fp"] <= 50


def test_vs_random_and_vs_all():
    ho = holdout_frame()
    info = compute_threshold(ho, {"benefit_tp": 40000, "action_cost": 1500, "fn_cost": 8000})
    y = ho["y_true"].to_numpy()
    ho["proba"].to_numpy()
    tp_all = int(np.sum(y == 1))
    fp_all = int(np.sum(y == 0))
    manual_all = tp_all * (40000 - 1500) - fp_all * 1500
    assert abs(manual_all - info["profit_all"]) < 0.01
    assert isinstance(info["vs_random"], float)


def test_regression_cost_saving():
    rng = np.random.default_rng(7)
    n = 1000
    y = rng.normal(100, 10, n)
    ho = pd.DataFrame({"y_true": y, "pred": y + 5})
    info = regression_cost(ho, {"cost_over": 2, "cost_under": 1})
    assert info["cost_total"] == round(float(2 * 5 * n), 2)
    assert info["saving"] > 0
