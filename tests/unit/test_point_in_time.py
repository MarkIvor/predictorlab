import duckdb
import numpy as np
import pandas as pd
from app.core.features.builder import build_feature_sql

CONFIG = {
    "main_table": "customers",
    "main_key": "id",
    "main_columns": ["segment"],
    "datetime_col": "signup_date",
    "snapshot_mode": "rolling",
    "n_snapshots": 3,
    "horizon_days": 30,
    "children": [
        {
            "table": "orders",
            "fk": "customer_id",
            "datetime_col": "order_date",
            "windows": [7, 90],
            "rfm": True,
            "agg_columns": [{"fn": "sum", "col": "amount"}],
        },
    ],
    "target": {"table": "orders", "fk": "customer_id", "datetime_col": "order_date", "type": "count_in_window", "min_count": 1},
}


def test_aggregates_only_before_t0():
    sql = build_feature_sql(CONFIG, snapshot_dates=["2024-06-01", "2024-09-01"], mode="rolling")
    agg_parts = [line for line in sql.splitlines() if "WHERE" in line and "t0 + INTERVAL 30 DAY" not in line]
    assert agg_parts, "нет агрегатных WHERE"
    for line in agg_parts:
        assert "< snap.t0" in line or "< s.t0" in line, f"агрегат без точки отсечки: {line}"


def test_target_uses_window_after_t0():
    sql = build_feature_sql(CONFIG, snapshot_dates=["2024-06-01"], mode="rolling")
    assert ">= snap.t0" in sql
    assert "< snap.t0 + INTERVAL 30 DAY" in sql


def test_no_aggregate_uses_events_after_t0():
    sql = build_feature_sql(CONFIG, snapshot_dates=["2024-06-01"], mode="rolling")
    for line in sql.splitlines():
        if "WHERE" in line and "t0 + INTERVAL 30 DAY" not in line and "a_target" not in line:
            assert ">= snap.t0" not in line.split("WHERE")[1].split("AND")[0] or "< snap.t0" in line


def test_sql_executes_and_values_are_point_in_time():
    np.random.default_rng(21)
    customers = pd.DataFrame(
        {
            "id": ["A", "B", "C"],
            "segment": ["SMB", "Ent", "Mid"],
            "signup_date": ["2023-01-01", "2023-02-01", "2023-03-01"],
        }
    )
    orders = pd.DataFrame(
        {
            "order_id": ["o1", "o2", "o3", "o4", "o5", "o6"],
            "customer_id": ["A", "A", "A", "B", "B", "C"],
            "order_date": ["2024-05-20", "2024-05-25", "2024-06-15", "2024-05-10", "2024-06-20", "2024-05-28"],
            "amount": [100.0, 200.0, 50.0, 10.0, 20.0, 30.0],
        }
    )
    con = duckdb.connect()
    con.register("customers", customers)
    con.register("orders", orders)
    sql = build_feature_sql(CONFIG, snapshot_dates=["2024-06-01"], mode="rolling")
    res = con.execute(sql).df()
    row_a = res[res["entity_id"] == "A"].iloc[0]
    assert row_a["orders__count_all_7d"] == 1, "в окно 7д до T0 попадает только 2024-05-25"
    assert row_a["orders__sum_amount_7d"] == 200.0
    assert row_a["orders__count_all_90d"] == 2, "90д окно: 05-20 и 05-25, но НЕ 06-15 (после T0)"
    assert row_a["target_count"] == 1, "таргет: заказ 06-15 в [06-01, 07-01)"
    row_b = res[res["entity_id"] == "B"].iloc[0]
    assert pd.isna(row_b["orders__count_all_7d"]) or row_b["orders__count_all_7d"] == 0, "нет событий в 7д окне → NULL/0"
    assert row_b["orders__count_all_90d"] == 1
    assert row_b["target_count"] == 1
    row_c = res[res["entity_id"] == "C"].iloc[0]
    assert bool(pd.isna(row_c["target_count"])), "нет событий в окне таргета → NULL (в билдере станет нулём)"
    assert row_c["orders__count_all_7d"] == 1
    con.close()


def test_per_entity_mode_uses_row_datetime():
    sql = build_feature_sql(CONFIG, mode="per_entity")
    assert 'TRY_CAST(e."signup_date" AS TIMESTAMP)' in sql
    assert "CROSS JOIN" not in sql
