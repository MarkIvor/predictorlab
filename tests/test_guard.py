import numpy as np
import pandas as pd
import pytest

from app.core.guard import checks as guard


def make_leaky_df(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(n)],
        "days_since_last_order": rng.integers(0, 200, n),
        "discount_pct": rng.normal(6, 3, n).round(1),
        "segment": rng.choice(["SMB", "Mid", "Ent"], n),
        "event_date": pd.date_range("2024-01-01", periods=n, freq="h").round("D"),
    })
    churn = rng.random(n) < 1 / (1 + np.exp(-(0.04 * (df["days_since_last_order"] - 40) - 0.1 * df["discount_pct"])))
    df["churn"] = churn.astype(int)
    cancel = pd.to_datetime(df["event_date"]) + pd.to_timedelta(rng.integers(2, 30, n), unit="D")
    df["cancel_date"] = np.where(df["churn"] == 1, cancel.astype(str), None)
    df["final_status"] = np.where(df["churn"] == 1, "расторжение", "активен")
    return df


def meta_for(df: pd.DataFrame) -> list[dict]:
    from app.core.ingest.typing import infer_column_meta
    return infer_column_meta(df)


def test_leak_block_names_both_columns():
    df = make_leaky_df()
    report = guard.run_pre_checks(df, "churn", "binary", "event_date", None, meta_for(df), ["customer_id"])
    assert report["verdict"] == "BLOCK"
    details = " ".join(c["detail"] for c in report["checks"])
    assert "cancel_date" in details
    assert "final_status" in details


def test_clean_data_not_block():
    df = make_leaky_df()[["days_since_last_order", "discount_pct", "segment", "event_date", "churn"]]
    report = guard.run_pre_checks(df, "churn", "binary", "event_date", None, meta_for(df), [])
    assert report["verdict"] in ("OK", "WARN")


def test_missingness_linked_to_target_blocks():
    rng = np.random.default_rng(1)
    n = 2000
    y = (rng.random(n) < 0.3).astype(int)
    df = pd.DataFrame({
        "num_ok": rng.normal(0, 1, n),
        "score": rng.normal(0, 1, n),
        "churn": y,
    })
    df.loc[df["churn"] == 1, "score"] = np.nan
    report = guard.run_pre_checks(df, "churn", "binary", None, None, meta_for(df), [])
    assert any(c["id"] == "missing_target_link" and c["verdict"] == "BLOCK" for c in report["checks"])


def test_future_feature_blocks():
    rng = np.random.default_rng(2)
    n = 2000
    event = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "churn": rng.integers(0, 2, n),
        "event_date": event,
        "later_call": event + pd.to_timedelta(rng.integers(10, 50, n), unit="D"),
    })
    report = guard.run_pre_checks(df, "churn", "binary", "event_date", None, meta_for(df), [])
    assert any(c["id"] == "future_feature" and c["verdict"] == "BLOCK" for c in report["checks"])


def test_post_checks_dominant_feature():
    drivers = [{"feature": "leak", "impact": 0.9}, {"feature": "a", "impact": 0.05}, {"feature": "b", "impact": 0.05}]
    metrics = {"roc_auc": 0.7}
    report = guard.run_post_checks("binary", metrics, drivers)
    assert report["verdict"] == "BLOCK"
    assert "leak" in report["checks"][0]["detail"]


def test_split_overlap_blocks_random_split():
    rng = np.random.default_rng(3)
    n = 500
    base = rng.normal(0, 1, (10, 2))
    rows = base[rng.integers(0, 10, n)]
    df = pd.DataFrame(rows, columns=["a", "b"])
    df["y"] = rng.integers(0, 2, n)
    report = guard.run_split_checks(df, ["a", "b"], "y", np.arange(100), np.arange(100, 150), None, split_kind="random")
    assert report["verdict"] == "BLOCK"


def test_split_overlap_warn_out_of_time():
    rng = np.random.default_rng(3)
    n = 500
    base = rng.normal(0, 1, (10, 2))
    rows = base[rng.integers(0, 10, n)]
    df = pd.DataFrame(rows, columns=["a", "b"])
    df["y"] = rng.integers(0, 2, n)
    report = guard.run_split_checks(df, ["a", "b"], "y", np.arange(100), np.arange(100, 150), None, split_kind="out_of_time")
    assert report["verdict"] == "WARN"
