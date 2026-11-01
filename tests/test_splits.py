import numpy as np
import pandas as pd

from app.core.training.splits import make_splits


def make_temporal_df(n: int = 3000, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="h"),
        "x": rng.normal(0, 1, n),
        "ent": [f"E{i % 100:03d}" for i in range(n)],
        "y": rng.integers(0, 2, n),
    })


def test_out_of_time_holdout_is_last_by_time():
    df = make_temporal_df()
    plan = make_splits(df, "y", "binary", "date", None)
    assert plan.kind == "out_of_time"
    dates = pd.to_datetime(df["date"])
    max_train = dates.iloc[plan.train_idx].max()
    min_holdout = dates.iloc[plan.holdout_idx].min()
    assert min_holdout >= max_train
    assert len(plan.holdout_idx) == int(0.2 * len(df))


def test_calib_disjoint_from_cv_folds():
    df = make_temporal_df()
    plan = make_splits(df, "y", "binary", "date", None)
    calib = set(plan.calib_idx)
    for tr, va in plan.cv:
        assert not (set(tr) & calib)
        assert not (set(va) & calib)
        assert not (set(tr) & set(va))
    assert not (set(plan.holdout_idx) & (set(plan.train_idx) | calib))


def test_random_split_stratified_holdout_rate():
    rng = np.random.default_rng(9)
    n = 4000
    df = pd.DataFrame({
        "x": rng.normal(0, 1, n),
        "y": rng.integers(0, 2, n),
    })
    plan = make_splits(df, "y", "binary", None, None)
    assert plan.kind == "random"
    rate_train = df.iloc[plan.train_idx]["y"].mean()
    rate_hold = df.iloc[plan.holdout_idx]["y"].mean()
    assert abs(rate_train - rate_hold) < 0.03


def test_group_split_entities_disjoint():
    df = make_temporal_df(n=2000)
    df["ent"] = [f"E{i // 10:03d}" for i in range(2000)]
    plan = make_splits(df, "y", "binary", None, "ent")
    assert plan.kind == "group"
    for tr, va in plan.cv:
        tr_ents = set(df.iloc[tr]["ent"])
        va_ents = set(df.iloc[va]["ent"])
        assert not (tr_ents & va_ents)


def test_baseline_majority_and_median():
    df = make_temporal_df()
    plan = make_splits(df, "y", "binary", None, None)
    assert plan.baseline["type"] == "majority"
    df_reg = df.copy()
    df_reg["y"] = np.linspace(0, 100, len(df_reg))
    plan_reg = make_splits(df_reg, "y", "regression", None, None)
    assert plan_reg.baseline["type"] == "median"
