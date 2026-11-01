"""E2E Feature Builder: реляционная БД → витрина → модель → entity_id-прогноз. Тест 13.3 (point-in-time)."""
import sqlite3
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DEMO = BASE_DIR / "demo-data"


def make_sqlite_db(path: Path):
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    for table in ("customers", "orders", "tickets"):
        df = pd.read_csv(DEMO / f"rel_{table}.csv")
        df.to_sql(table, con, index=False, if_exists="replace")
    con.close()


def main():
    import os
    db_path = DEMO / f"rel_{os.getpid()}.db"
    make_sqlite_db(db_path)

    client = httpx.Client(base_url="http://localhost:8200", timeout=900)
    r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    assert r.status_code == 200, r.text

    print("== 1. Подключение к SQLite (read-only) ==")
    r = client.post("/api/connections", json={
        "name": "rel_demo", "db_type": "sqlite",
        "params": {"database": str(db_path)}})
    assert r.status_code == 201, r.text
    conn_id = r.json()["id"]
    r = client.post(f"/api/connections/{conn_id}/test")
    assert r.json()["ok"], r.text
    print("  PASS connection ok, tables:", len(r.json()["tables"]))

    print("== 2. Сборка витрины (rolling snapshots, горизонт 45 дней) ==")
    config = {
        "connection_id": conn_id,
        "main_table": "customers",
        "main_key": "customer_id",
        "main_columns": ["segment", "region", "discount_pct"],
        "datetime_col": "signup_date",
        "snapshot_mode": "rolling",
        "n_snapshots": 4,
        "horizon_days": 45,
        "children": [
            {"table": "orders", "fk": "customer_id", "datetime_col": "order_date",
             "windows": [7, 30, 90], "rfm": True,
             "agg_columns": [{"fn": "sum", "col": "amount"}, {"fn": "mean", "col": "amount"}]},
            {"table": "tickets", "fk": "customer_id", "datetime_col": "created_at",
             "windows": [30, 90], "rfm": False},
        ],
        "target": {"table": "orders", "fk": "customer_id", "datetime_col": "order_date",
                   "type": "count_in_window", "min_count": 1},
    }
    r = client.post("/api/features/build", json={"name": "b2b_mart", "config": config})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    assert jr["status"] == "done", str(jr)[:400]
    dataset_id = jr["progress"].get("dataset_id")
    assert dataset_id, str(jr)[:300]
    print(f"  PASS витрина собрана: {jr['progress'].get('nrows')} строк")

    print("== 3. SQL всегда виден: point-in-time (тест 13.3) ==")
    r = client.get(f"/api/datasets/{dataset_id}/feature-sql")
    sql = r.json()["sql"]
    assert sql, "SQL витрины пуст"
    agg_blocks = sql.count("< snap.t0")
    target_window = ("WHERE TRY_CAST(c." in sql) and (f"INTERVAL 45 DAY" in sql)
    assert agg_blocks >= 4, f"агрегатов с < snap.t0 должно быть много, найдено {agg_blocks}"
    assert "AND" in sql and ">= snap.t0" in sql, "таргет должен считать окно [t0, t0+horizon)"
    banned = [line for line in sql.splitlines() if ">= snap.t0" in line and "t0 + INTERVAL" not in line and "a_target" not in sql and line.strip().startswith("WHERE")]
    ok_windows = all(("< snap.t0" in line) for line in sql.splitlines() if "WHERE" in line and "INTERVAL" in line and "t0 + INTERVAL 45" not in line)
    assert ok_windows, "у каждого агрегата нижняя граница окна, но события только < snap.t0"
    print(f"  PASS point-in-time: {agg_blocks} агрегатов с '< snap.t0', таргет в окне [t0, t0+45)")

    print("== 4. Модель на витрине: out-of-time по snapshot-датам ==")
    r = client.get(f"/api/datasets/{dataset_id}")
    ds = r.json()
    assert ds["entity_col"] == "customer_id" and ds["event_time_col"] == "t0"
    r = client.post("/api/models", json={"dataset_id": dataset_id, "name": "b2b_buy45",
                                         "target_col": "target", "event_time_col": "t0"})
    assert r.status_code == 201, r.text[:300]
    model = r.json()
    model_id = model["id"]
    assert model["guard_report"]["split_kind"] == "out_of_time", model["guard_report"]
    excluded = list(model["excluded_cols"])
    r = client.patch(f"/api/models/{model_id}", json={"excluded_cols": []})
    r = client.post(f"/api/models/{model_id}/train", json={"mode": "quick"})
    assert r.status_code == 201, r.text[:300]
    train_job = r.json()["job_id"]
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        jr = client.get(f"/api/jobs/{train_job}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    assert jr["status"] == "done", str(jr)[:400]
    r = client.get(f"/api/models/{model_id}")
    metrics = r.json().get("metrics") or {}
    auc = metrics.get("roc_auc")
    base_rate = metrics.get("base_rate")
    print(f"  PASS обучено, ROC-AUC={auc}, base_rate={base_rate}")
    assert base_rate and 0.05 < base_rate < 0.9, f"таргет вырожден: base_rate={base_rate}"
    assert auc and 0.55 < auc < 0.95, f"странный AUC {auc}"

    print("== 5. Прогноз по entity_id (T0 = сегодня) ==")
    r = client.get(f"/api/datasets/{dataset_id}")
    some_entity = None
    for col_meta in r.json()["columns"]:
        if col_meta["name"] == "entity_id":
            some_entity = (col_meta.get("sample") or [""])[0]
            break
    r = client.post(f"/api/datasets/{dataset_id}/entity-preview", json={"entity_id": some_entity})
    assert r.status_code == 200, r.text[:300]
    feats = r.json()["features"]
    assert "orders__count_all_90d" in feats or any("orders__" in k for k in feats), str(list(feats)[:10])
    print(f"  PASS entity-preview для {some_entity}: {len(feats)} фичей из БД на текущий момент")

    print("  ALL FEATURES E2E PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
