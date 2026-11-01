import json
from datetime import timedelta

import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.monitor.drift import psi_frame, status_from_psi
from app.models.database import (Dataset, DriftReport, Feedback, Job, Model, ModelVersion,
                                 PredictionLog, SessionLocal, Webhook, utcnow)


def _emit(job_id, ev_type, data):
    from app.models.database import JobEvent
    db = SessionLocal()
    try:
        db.add(JobEvent(job_id=job_id, type=ev_type, data=data))
        db.commit()
    finally:
        db.close()


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


def run(job_id: str):
    settings = get_settings()
    db = SessionLocal()
    job = db.get(Job, job_id)
    payload = dict(job.payload or {})
    model = db.get(Model, job.model_id)
    version = db.get(ModelVersion, payload.get("version_id") or model.active_version_id)
    window_days = int(payload.get("window_days", 30))
    db.close()

    vdir = settings.storage_path / version.dir_path
    reference = pd.read_parquet(vdir / "shap_background.parquet") if (vdir / "shap_background.parquet").exists() else None
    categorical = (version.manifest or {}).get("categorical_cols") or []
    holdout_path = vdir / "holdout_preds.parquet"

    since = utcnow() - timedelta(days=window_days)
    db = SessionLocal()
    logs = db.query(PredictionLog).filter(
        PredictionLog.model_id == model.id, PredictionLog.version_id == version.id,
        PredictionLog.created_at >= since).all()
    db.close()

    psi_features: dict = {}
    psi_prediction = None
    status = "OK"
    live_metrics: dict = {}
    live_alert = False

    if reference is not None and len(logs) >= 50:
        records = pd.DataFrame([l.input or {} for l in logs])
        from app.core.training import preprocess as prep
        spec = {"numeric": [c for c in reference.columns if c not in categorical],
                "boolean": [], "datetime": {}, "categorical": categorical, "text": []}
        try:
            current = prep.transform(records, spec)
            current = current.reindex(columns=reference.columns, axis=1)
            psi_features = psi_frame(reference, current, categorical)
        except Exception:
            psi_features = {}
        statuses = [status_from_psi(v, settings.drift_psi_warn, settings.drift_psi_drift)
                    for v in psi_features.values()]
        if "DRIFT" in statuses:
            status = "DRIFT"
        elif "WARN" in statuses:
            status = "WARN"
        _progress(job_id, psi_features={k: (round(v, 4) if v else None) for k, v in list(psi_features.items())[:50]})

    if holdout_path.exists() and len(logs) >= 50:
        ho = pd.read_parquet(holdout_path)
        prob_col = "proba" if "proba" in ho.columns else None
        if prob_col:
            cur_probs = np.array([float((l.output or {}).get("probability", 0) or 0) for l in logs])
            from app.core.monitor.drift import psi_numeric
            psi_prediction = psi_numeric(ho[prob_col].to_numpy(dtype=float), cur_probs)
            s = status_from_psi(psi_prediction, settings.drift_psi_warn, settings.drift_psi_drift)
            if s == "DRIFT":
                status = "DRIFT"
            elif s == "WARN" and status == "OK":
                status = "WARN"

    db = SessionLocal()
    feedbacks = db.query(Feedback).filter(Feedback.model_id == model.id,
                                           Feedback.created_at >= since).all()
    db.close()
    if len(feedbacks) >= 30:
        fb_by_pred = {f.prediction_id: f for f in feedbacks if f.prediction_id}
        rows = []
        for log in logs:
            fb = fb_by_pred.get(log.prediction_id)
            if fb is None:
                continue
            prob = (log.output or {}).get("probability")
            if prob is None:
                continue
            actual = fb.actual_numeric if fb.actual_numeric is not None else (1.0 if str(fb.actual_label) in ("1", "True", "yes", "да") else (0.0 if str(fb.actual_label) in ("0", "False", "no", "нет") else None))
            if actual is None:
                continue
            rows.append((float(prob), float(actual)))
        if len(rows) >= 30:
            probs, actuals = zip(*rows)
            try:
                from sklearn.metrics import roc_auc_score
                auc = float(roc_auc_score(actuals, probs))
                live_metrics["live_auc"] = round(auc, 4)
                val_auc = (version.metrics or {}).get("roc_auc")
                if val_auc and auc < float(val_auc) - 0.1:
                    live_alert = True
                    live_metrics["alert"] = f"Live AUC {auc:.3f} упала более чем на 10 п.п. относительно валидации ({val_auc:.3f})"
            except Exception:
                pass

    report = {
        "n_predictions": len(logs),
        "n_feedback": len(feedbacks),
        "psi_features": psi_features,
        "psi_prediction": round(psi_prediction, 4) if psi_prediction is not None else None,
        "live_metrics": live_metrics,
        "thresholds": {"warn": settings.drift_psi_warn, "drift": settings.drift_psi_drift},
    }
    db = SessionLocal()
    db.add(DriftReport(model_id=model.id, window_days=window_days, status=status,
                       psi_features={k: (round(v, 4) if v is not None else None) for k, v in psi_features.items()},
                       psi_prediction=round(psi_prediction, 4) if psi_prediction is not None else None,
                       live_metrics=live_metrics, report=report))
    db.commit()
    db.close()

    if status == "DRIFT" or live_alert:
        _fire_webhooks(model.id, {
            "event": "drift" if status == "DRIFT" else "live_metric_drop",
            "model_id": model.id, "status": status, "live_metrics": live_metrics,
        })
    _progress(job_id, status=status)
    return {"status": status, "n_predictions": len(logs)}


def _fire_webhooks(model_id: int, payload: dict):
    db = SessionLocal()
    hooks = db.query(Webhook).filter(Webhook.active == True).all()  # noqa: E712
    db.close()
    import httpx
    for hook in hooks:
        if hook.model_id and hook.model_id != model_id:
            continue
        try:
            httpx.post(hook.url, json=payload, timeout=10)
        except Exception:
            continue
