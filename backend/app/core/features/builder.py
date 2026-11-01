import json
from typing import Any

import duckdb
import pandas as pd

from app.config import get_settings
from app.core.ingest.loader import ingest_dataframe
from app.models.database import Connection, Dataset, Job, SessionLocal
from app.services.ensure import require
from app.services.security import decrypt_str

WINDOWS = (7, 30, 90)


def _q(ident: object) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


def _emit(job_id: str, ev_type: str, data: dict) -> None:
    from app.models.database import JobEvent

    db = SessionLocal()
    try:
        db.add(JobEvent(job_id=job_id, type=ev_type, data=data))
        db.commit()
    finally:
        db.close()


def _progress(job_id: str, **fields: object) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            prog = dict(job.progress or {})
            prog.update(fields)
            job.progress = prog
            db.commit()
    finally:
        db.close()


def connection_connector(conn_row: Connection) -> Any:
    from app.services.connectors.registry import get_connector

    params = json.loads(decrypt_str(conn_row.params_enc))
    return get_connector(conn_row.name, conn_row.db_type, params)


def default_aggs(child: dict) -> list[dict]:
    aggs = [{"fn": "count", "col": "*"}]
    for spec in child.get("agg_columns") or []:
        if spec.get("fn") in ("sum", "mean", "max", "min", "nunique") and spec.get("col"):
            aggs.append({"fn": spec["fn"], "col": spec["col"]})
    return aggs


def _snap_sql(config: dict, mode: str, snapshot_dates: list[str], entity_ids: list[str] | None) -> str:
    main = _q(config["main_table"])
    key = _q(config["main_key"])
    main_dt = _q(config["datetime_col"]) if config.get("datetime_col") else None
    if mode == "rolling":
        values = ", ".join(f"(TIMESTAMP '{d}')" for d in snapshot_dates)
        exists_clause = f"WHERE TRY_CAST(e.{main_dt} AS TIMESTAMP) < s.t0" if main_dt else ""
        return f"SELECT e.{key} AS entity_id, s.t0 AS t0 FROM {main} AS e CROSS JOIN (VALUES {values}) AS s(t0) {exists_clause}"
    t0_expr = f"TRY_CAST(e.{main_dt} AS TIMESTAMP)" if main_dt else "CURRENT_DATE"
    filt = ""
    if entity_ids:
        ids = ", ".join("'" + str(e).replace("'", "''") + "'" for e in entity_ids)
        filt = f"WHERE CAST(e.{key} AS VARCHAR) IN ({ids})"
    return f"SELECT e.{key} AS entity_id, {t0_expr} AS t0 FROM {main} AS e {filt}"


def build_feature_sql(config: dict, snapshot_dates: list[str] | None = None, mode: str | None = None, entity_ids: list[str] | None = None) -> str:
    """Point-in-time гарантия: каждый агрегат — только события < t0; таргет — окно [t0, t0 + horizon)."""
    mode = mode or config.get("snapshot_mode", "rolling")
    horizon = int(config.get("horizon_days", 45))
    main = _q(config["main_table"])
    key = _q(config["main_key"])

    ctes: list[tuple[str, str]] = []
    joins: list[str] = []
    selects: list[str] = ["snap.entity_id", "snap.t0"]

    snap_sql = _snap_sql(config, mode, snapshot_dates or [], entity_ids)
    ctes.append(("snap", snap_sql))

    for col in config.get("main_columns") or []:
        selects.append(f"e.{_q(col)}")

    def add_agg_cte(alias: str, table: str, fk: str, dt_col: str, cols: list[tuple[str, str]], lower_bound: str | None) -> None:
        dt_expr = f"TRY_CAST(c.{_q(dt_col)} AS TIMESTAMP)"
        where = f"{dt_expr} < snap.t0"
        if lower_bound:
            where += f" AND {dt_expr} >= {lower_bound}"
        inner = (
            f"SELECT snap.entity_id, snap.t0, {', '.join(expr + ' AS ' + _q(name) for name, expr in cols)} "
            f"FROM snap JOIN {_q(table)} AS c ON CAST(c.{_q(fk)} AS VARCHAR) = CAST(snap.entity_id AS VARCHAR) "
            f"WHERE {where} GROUP BY snap.entity_id, snap.t0"
        )
        ctes.append((alias, inner))
        joins.append(f"LEFT JOIN {alias} ON {alias}.entity_id = snap.entity_id AND {alias}.t0 = snap.t0")
        for name, _ in cols:
            selects.append(f"{alias}.{_q(name)} AS {_q(name)}")

    for child in config.get("children", []):
        table = child["table"]
        windows = child.get("windows") or list(WINDOWS)
        for w in windows:
            cols: list[tuple[str, str]] = []
            for spec in default_aggs(child):
                fn, col = spec["fn"], spec.get("col", "*")
                safe_col = (col if col != "*" else "all").replace('"', "").replace(" ", "_")
                name = f"{table}__{fn}_{safe_col}_{w}d"
                if fn == "count":
                    expr = "COUNT(*)"
                elif fn == "nunique":
                    expr = f"COUNT(DISTINCT c.{_q(col)})"
                else:
                    expr = f"{fn.upper()}(TRY_CAST(c.{_q(col)} AS DOUBLE))"
                cols.append((name, expr))
            dt = child["datetime_col"]
            dt_expr = f"TRY_CAST(c.{_q(dt)} AS TIMESTAMP)"
            cols.append((f"{table}__days_since_last_{w}d", f"DATE_DIFF('day', MAX({dt_expr}), snap.t0)"))
            add_agg_cte(f"a_{table}_{w}d", table, child["fk"], dt, cols, f"snap.t0 - INTERVAL {int(w)} DAY")

        if child.get("rfm"):
            dt = child["datetime_col"]
            dt_expr = f"TRY_CAST(c.{_q(dt)} AS TIMESTAMP)"
            rfm_cols = [(f"{table}__recency", f"DATE_DIFF('day', MAX({dt_expr}), snap.t0)"), (f"{table}__frequency", "COUNT(*)")]
            for spec in child.get("agg_columns") or []:
                if spec.get("fn") == "sum" and spec.get("col"):
                    rfm_cols.append((f"{table}__monetary", f"SUM(TRY_CAST(c.{_q(spec['col'])} AS DOUBLE))"))
            add_agg_cte(f"a_{table}_rfm", table, child["fk"], dt, rfm_cols, None)

    target = config.get("target") or {}
    target_col = None
    if target.get("table"):
        dt = target["datetime_col"]
        dt_expr = f"TRY_CAST(c.{_q(dt)} AS TIMESTAMP)"
        if target.get("type", "count_in_window") == "count_in_window":
            target_col = "target_count"
            expr = "COUNT(*)"
        else:
            target_col = "target_sum"
            expr = f"SUM(TRY_CAST(c.{_q(target.get('column', 'amount'))} AS DOUBLE))"
        inner = (
            f"SELECT snap.entity_id, snap.t0, {expr} AS {_q(target_col)} "
            f"FROM snap JOIN {_q(target['table'])} AS c "
            f"ON CAST(c.{_q(target.get('fk') or 'customer_id')} AS VARCHAR) = CAST(snap.entity_id AS VARCHAR) "
            f"WHERE {dt_expr} >= snap.t0 AND {dt_expr} < snap.t0 + INTERVAL {horizon} DAY "
            f"GROUP BY snap.entity_id, snap.t0"
        )
        ctes.append(("a_target", inner))
        joins.append("LEFT JOIN a_target ON a_target.entity_id = snap.entity_id AND a_target.t0 = snap.t0")
        selects.append(f"a_target.{_q(target_col)} AS {_q(target_col)}")

    cte_sql = ",\n".join(f"{alias} AS (\n  {inner}\n)" for alias, inner in ctes)
    sql = (
        "WITH "
        + cte_sql
        + "\n"
        + "SELECT "
        + ", ".join(selects)
        + "\n"
        + f"FROM snap JOIN {main} AS e ON CAST(e.{key} AS VARCHAR) = CAST(snap.entity_id AS VARCHAR)\n"
        + ("\n".join(joins) if joins else "")
    )
    return sql


def _snapshots_for_training(duck: Any, config: dict) -> list[str]:
    target = config.get("target") or {}
    if not target.get("table"):
        return []
    horizon = int(config.get("horizon_days", 45))
    t, dt = target["table"], target["datetime_col"]
    row = duck.execute(f"SELECT MIN(TRY_CAST({_q(dt)} AS TIMESTAMP)), MAX(TRY_CAST({_q(dt)} AS TIMESTAMP)), COUNT(*) FROM {_q(t)}").fetchone()
    lo, hi, total = row
    if lo is None or hi is None:
        return []
    last_t0 = hi - pd.Timedelta(days=horizon)
    if last_t0 <= lo:
        return [lo.strftime("%Y-%m-%d")]
    n = max(2, int(config.get("n_snapshots", 4)))
    candidates = pd.date_range(lo, last_t0, periods=n * 2)[1:]
    valid: list[str] = []
    for t0 in candidates:
        try:
            cnt = duck.execute(
                f"SELECT COUNT(*) FROM {_q(t)} WHERE TRY_CAST({_q(dt)} AS TIMESTAMP) >= TIMESTAMP '{t0.date()}' "
                f"AND TRY_CAST({_q(dt)} AS TIMESTAMP) < TIMESTAMP '{t0.date()}' + INTERVAL {horizon} DAY"
            ).fetchone()[0]
        except Exception:
            cnt = 0
        if cnt >= max(50, int(total * 0.002)):
            valid.append(t0.strftime("%Y-%m-%d"))
        if len(valid) >= n:
            break
    return valid


def _fetch_tables(duck: Any, conn: Any, config: dict, settings: Any) -> dict:
    tables = [config["main_table"]] + [c["table"] for c in config.get("children", [])]
    if (config.get("target") or {}).get("table"):
        tables.append(config["target"]["table"])
    fetched = {}
    for table in dict.fromkeys(tables):
        df = conn.fetch_table(table, limit=settings.max_rows)
        duck.register(f"src_{table}", df)
        duck.execute(f"CREATE OR REPLACE TABLE {_q(table)} AS SELECT * FROM src_{table}")
        fetched[table] = df
    return fetched


def run(job_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    job = require(db.get(Job, job_id), f"Задача {job_id} не найдена")
    payload = dict(job.payload or {})
    config = payload["config"]
    user_id = job.user_id
    name = payload.get("name") or "Витрина"
    db.close()

    db = SessionLocal()
    conn_row = require(db.get(Connection, int(config["connection_id"])), "Подключение не найдено")
    db.close()

    duck = duckdb.connect()
    _progress(job_id, stage="fetch", message="Выгружаю таблицы из БД")
    conn = connection_connector(conn_row)
    fetched = _fetch_tables(duck, conn, config, settings)
    for table, df in fetched.items():
        _progress(job_id, message=f"Выгружено: {table} ({len(df):,} строк)".replace(",", " "))

    mode = config.get("snapshot_mode", "rolling")
    snapshot_dates = _snapshots_for_training(duck, config) if mode == "rolling" else None
    if mode == "rolling" and not snapshot_dates:
        raise RuntimeError("Не удалось определить даты срезов: проверьте datetime-колонку таблицы таргета")
    sql = build_feature_sql(config, snapshot_dates=snapshot_dates, mode=mode)
    _progress(job_id, stage="build", message="Считаю витрину по точке отсечки")
    result = duck.execute(sql).df()
    if result.empty:
        raise RuntimeError("Витрина пуста — проверьте ключи связей и даты")

    target = config.get("target") or {}
    if target.get("type", "count_in_window") == "count_in_window" and "target_count" in result.columns:
        min_count = int(target.get("min_count", 1))
        result["target"] = (result["target_count"].fillna(0) >= min_count).astype(int)
        result = result.drop(columns=["target_count"])
    elif "target_sum" in result.columns:
        result["target"] = result["target_sum"].fillna(0)
        result = result.rename(columns={})
        result = result.drop(columns=["target_sum"])
    result = result.reset_index(drop=True)

    dataset_id, nrows, ncols, columns_meta, data_hash, health = ingest_dataframe(result)
    out_dir = settings.datasets_path / dataset_id
    for table in fetched:
        try:
            duck.execute(f"COPY (SELECT * FROM {_q(table)}) TO '{(out_dir / ('src_' + table + '.parquet')).as_posix()}' (FORMAT PARQUET)")
        except Exception:
            pass

    s = SessionLocal()
    try:
        for col in columns_meta:
            if col["name"] == config["main_key"]:
                col["type"] = "id"
                col["excluded"] = True
                col["exclude_reason"] = "ID сущности"
        d = Dataset(
            id=dataset_id,
            user_id=user_id,
            name=name,
            source_type="features",
            file_path=str((out_dir / "data.parquet").relative_to(settings.storage_path)),
            nrows=nrows,
            ncols=ncols,
            columns_meta=columns_meta,
            data_hash=data_hash,
            health=health,
            entity_col=config["main_key"],
            event_time_col="t0",
            connection_id=conn_row.id,
            feature_config=config,
            feature_sql=sql,
        )
        s.add(d)
        s.commit()
        dataset_pk = d.id
    finally:
        s.close()

    _progress(job_id, stage="done", dataset_id=dataset_pk, nrows=nrows)
    return {"dataset_id": dataset_pk, "nrows": nrows, "ncols": ncols}


def features_for_entities(dataset: Dataset, entity_ids: list[str]) -> pd.DataFrame:
    """Прогноз по entity_id: свежие данные из БД, T0 = CURRENT_DATE."""
    settings = get_settings()
    config = dataset.feature_config or {}
    db = SessionLocal()
    conn_row = require(db.get(Connection, int(config.get("connection_id") or 0)), "Подключение не найдено")
    db.close()
    duck = duckdb.connect()
    conn = connection_connector(conn_row)
    _fetch_tables(duck, conn, config, settings)
    sql = build_feature_sql(config, mode="per_entity", entity_ids=entity_ids)
    df = duck.execute(sql).df()
    duck.close()
    for drop_col in ("target_count", "target_sum"):
        if drop_col in df.columns:
            df = df.drop(columns=[drop_col])
    return df
