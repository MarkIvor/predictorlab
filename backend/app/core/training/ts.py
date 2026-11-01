import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.config import get_settings
from app.core.registry import artifacts
from app.core.uncertainty import conformal as conf
from app.core.uncertainty import ood as ood_mod
from app.models.database import Dataset, Job, Model, ModelVersion, SessionLocal


def _progress(job_id, **fields):
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


LAGS = (1, 2, 3, 7, 14, 30)
ROLLS = (7, 30)


def build_ts_features(y: pd.Series, dt: pd.Series) -> pd.DataFrame:
    x = pd.DataFrame(index=y.index)
    for lag in LAGS:
        x[f"lag_{lag}"] = y.shift(lag)
    for w in ROLLS:
        x[f"roll_mean_{w}"] = y.shift(1).rolling(w, min_periods=1).mean()
        x[f"roll_std_{w}"] = y.shift(1).rolling(w, min_periods=2).std()
    d = pd.to_datetime(dt, errors="coerce")
    x["dt_year"] = d.dt.year.astype(float)
    x["dt_month"] = d.dt.month.astype(float)
    x["dt_dayofweek"] = d.dt.dayofweek.astype(float)
    x["dt_day"] = d.dt.day.astype(float)
    return x


def run(job_id: str, model_id: int, dataset_ref: str, mode: str):
    settings = get_settings()
    db = SessionLocal()
    job = db.get(Job, job_id)
    model = db.get(Model, model_id)
    dataset = db.get(Dataset, dataset_ref)
    db.close()

    from app.core.ingest import io as ds_io
    df = ds_io.load_dataset_df(str(settings.storage_path / dataset.file_path))
    time_col = dataset.event_time_col
    if not time_col or time_col not in df.columns:
        raise RuntimeError("Для прогноза временных рядов нужна колонка времени события (задайте её в датасете)")
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col, model.target_col]).sort_values(time_col).reset_index(drop=True)
    y = pd.to_numeric(df[model.target_col], errors="coerce")
    keep = y.notna()
    df, y = df[keep].reset_index(drop=True), y[keep].reset_index(drop=True)
    if len(df) < 60:
        raise RuntimeError("Для временного ряда нужно минимум 60 точек")

    n = len(y)
    n_hold = max(5, int(n * 0.2))
    n_calib = max(5, int(n * 0.1))
    holdout_start = n - n_hold
    calib_start = holdout_start - n_calib

    X = build_ts_features(y, df[time_col])
    feature_cols = [c for c in X.columns if not c.startswith("dt_")]
    fit_end = calib_start
    X_fit, y_fit = X.iloc[:fit_end], y.iloc[:fit_end]
    X_cal, y_cal = X.iloc[calib_start:holdout_start], y.iloc[calib_start:holdout_start]

    naive_preds_cal = y.shift(1).iloc[calib_start:holdout_start]
    naive_mae = mean_absolute_error(y_cal, naive_preds_cal)
    snaive_preds_cal = y.shift(7).iloc[calib_start:holdout_start]
    snaive_mae = mean_absolute_error(y_cal, snaive_preds_cal)

    cb_mae = np.inf
    est = None
    if fit_end > 50:
        from catboost import CatBoostRegressor
        est = CatBoostRegressor(iterations=settings.quick_iterations if mode == "quick" else 800,
                                depth=4, learning_rate=0.05, random_seed=settings.seed,
                                verbose=False, thread_count=-1, allow_writing_files=False)
        est.fit(X_fit, y_fit)
        cb_preds_cal = est.predict(X_cal)
        cb_mae = mean_absolute_error(y_cal, cb_preds_cal)

    candidates = [
        {"name": "naive", "kind": "naive", "mae": float(naive_mae)},
        {"name": "seasonal_naive_7", "kind": "snaive", "mae": float(snaive_mae)},
    ]
    if est is not None:
        candidates.append({"name": "catboost", "kind": "catboost", "mae": float(cb_mae)})
    candidates.sort(key=lambda c: c["mae"])
    best = candidates[0]
    _progress(job_id, candidates=[{k: round(v, 4) if isinstance(v, float) else v for k, v in c.items()} for c in candidates])

    def predict_at(i: int) -> float:
        if best["kind"] == "naive":
            return float(y.iloc[i - 1])
        if best["kind"] == "snaive":
            return float(y.iloc[i - 7])
        row = X.iloc[[i]]
        return float(est.predict(row)[0])

    calib_res = np.abs(y_cal - np.array([predict_at(i) for i in range(calib_start, holdout_start)]))
    conformal = conf.calibrate_regression(np.zeros(len(calib_res)), calib_res * 0 + calib_res, alpha=0.9)

    preds, intervals = [], []
    for i in range(holdout_start, n):
        p = predict_at(i)
        lo, hi = conf.regression_interval(p, conformal)
        preds.append(p)
        intervals.append((lo, hi))
    y_ho = y.iloc[holdout_start].to_numpy()
    preds = np.array(preds)
    mae = mean_absolute_error(y_ho, preds)
    rmse = float(np.sqrt(mean_squared_error(y_ho, preds)))
    mape = None
    if not np.any(np.abs(y_ho) < 1e-9):
        mape = float(np.mean(np.abs((y_ho - preds) / y_ho)) * 100)
    covered = np.array([lo <= yy <= hi for (lo, hi), yy in zip(intervals, y_ho)])

    metrics = {
        "task_type": "timeseries",
        "mae": float(mae), "rmse": rmse, "mape": mape,
        "baseline": {"type": "naive", "detail": "naive: последнее значение"},
        "baseline_mae": float(naive_mae),
        "lift_pct": round((naive_mae - mae) / max(naive_mae, 1e-9) * 100, 2),
        "coverage": float(covered.mean()),
        "coverage_target": conformal["alpha"],
        "n_holdout": int(n_hold),
        "best_model": best["name"],
        "candidates": candidates,
    }

    holdout_frame = pd.DataFrame({
        "y_true": y_ho, "pred": preds,
        "interval_low": [i[0] for i in intervals], "interval_high": [i[1] for i in intervals],
        "ood": [False] * n_hold,
        "event_time": df[time_col].iloc[holdout_start:].astype(str).to_numpy(),
    })

    db = SessionLocal()
    try:
        db_model = db.get(Model, model_id)
        prev = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).order_by(ModelVersion.version.desc()).first()
        version = (prev.version + 1) if prev else 1
        vdir = artifacts.version_dir(model_id, version)
        vdir.mkdir(parents=True, exist_ok=True)

        spec = {"numeric": list(X.columns), "boolean": [], "datetime": {}, "categorical": [], "text": [],
                "feature_cols": list(X.columns), "target_col": model.target_col,
                "ts": {"lags": list(LAGS), "rolls": list(ROLLS)}}
        artifacts.save_joblib(vdir, "pipeline.joblib", {
            "kind": "ts", "estimator": est, "best": best, "spec": spec,
            "task_type": "timeseries", "classes": None, "calibrator": None,
        })
        artifacts.save_joblib(vdir, "conformal.joblib", conformal)
        artifacts.save_joblib(vdir, "ood.joblib", {})
        holdout_frame.to_parquet(vdir / "holdout_preds.parquet", index=False)
        X_fit.tail(500).to_parquet(vdir / "shap_background.parquet", index=False)
        properties = {c: {"type": "number", "title": c} for c in X.columns}
        artifacts.save_json(vdir, "schema.json", {
            "input_schema": {"type": "object", "properties": properties, "required": [],
                             "additionalProperties": True},
            "example": {c: None for c in X.columns},
            "target": {"column": model.target_col, "classes": None},
            "history_schema": {"type": "array", "description": "история значений ряда от старых к новым"},
        })
        artifacts.save_json(vdir, "metrics.json", metrics)
        leakage = {"pre": db_model.guard_report or {}, "split": {"verdict": "OK", "checks": []},
                   "post": {"verdict": "OK", "checks": []}, "verdict": (db_model.guard_report or {}).get("verdict", "OK"),
                   "guard_override": bool(job.payload.get("guard_override"))}
        artifacts.save_json(vdir, "leakage_report.json", leakage)
        manifest = {
            "model_id": model_id, "version": version, "task_type": "timeseries", "mode": mode,
            "seed": settings.seed, "deterministic": settings.deterministic,
            "data_hash": dataset.data_hash, "nrows": int(len(df)),
            "split": {"kind": "out_of_time", "n_holdout": n_hold, "n_calib": n_calib,
                      "baseline": {"type": "naive", "detail": "naive: последнее значение"}},
            "candidates": candidates,
        }
        artifacts.write_manifest(vdir, manifest)
        mv = ModelVersion(model_id=model_id, version=version,
                          dir_path=str(vdir.relative_to(settings.storage_path)),
                          manifest=manifest, metrics=metrics, leakage_report=leakage, status="ready")
        db.add(mv)
        db.flush()
        db_model.status = "ready"
        db_model.active_version_id = mv.id
        db.commit()
        version_id = mv.id
    finally:
        db.close()
    _progress(job_id, stage="done", version=version)
    return {"version": version, "version_id": version_id}


def forecast_from_history(pipeline: dict, history: list[float], horizon: int = 1) -> list[dict]:
    y = pd.Series([float(v) for v in history if v is not None])
    if len(y) < max(LAGS) + 1:
        raise ValueError(f"Нужно минимум {max(LAGS) + 1} точек истории")
    est = pipeline.get("estimator")
    best = pipeline.get("best") or {"kind": "catboost"}
    now = pd.Timestamp.now()
    results = []
    for step in range(horizon):
        dt = pd.Series([now] + list(pd.Timestamp.now() for _ in range(len(y))))
        x = build_ts_features(y, pd.Series([now] * (len(y) + 1)))
        row = x.iloc[[-1]]
        if best.get("kind") == "naive" or est is None and best.get("kind") != "snaive":
            pred = float(y.iloc[-1])
        elif best.get("kind") == "snaive":
            pred = float(y.iloc[-7]) if len(y) >= 7 else float(y.iloc[-1])
        else:
            pred = float(est.predict(row)[0])
        results.append({"step": step + 1, "prediction": round(pred, 4)})
        y = pd.concat([y, pd.Series([pred])], ignore_index=True)
    return results
