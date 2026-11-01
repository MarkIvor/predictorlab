import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import check_model_access, get_api_key_or_user, get_db
from app.config import get_settings
from app.core.business.counterfactual import find_counterfactual
from app.core.predict import engine
from app.core.predict.batch import run as batch_run  # noqa: F401
from app.jobs import queue
from app.models.database import Dataset, DriftReport, Feedback, Job, Model, ModelVersion, PredictionLog
from app.services import pii as pii_service
from app.services.metrics import PREDICT_LATENCY, PREDICT_REQUESTS

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


class PredictIn(BaseModel):
    data: list[dict] = Field(min_length=1, max_length=1000)
    include: list[str] = Field(default_factory=list)
    version: int | None = None


class ExplainIn(BaseModel):
    data: dict
    version: int | None = None


class WhatIfIn(BaseModel):
    data: dict
    changes: dict
    version: int | None = None


class CounterfactualIn(BaseModel):
    data: dict
    direction: str = Field(default="below", pattern="^(below|above)$")
    version: int | None = None


class FeedbackIn(BaseModel):
    prediction_id: str | None = None
    entity_id: str | None = None
    actual: object = None


def _get_model(model_id: int, principal: Any, kind: str, db: Session) -> Model:
    m = db.get(Model, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    if kind == "key":
        check_model_access(principal, kind, m.user_id, m.id)  # type: ignore[arg-type]
    else:
        if principal.role != "admin" and m.user_id != principal.id:
            raise HTTPException(status_code=403, detail="Модель недоступна")
    return m


def _pick_version(model: Model, version_num: int | None, db: Session) -> ModelVersion:
    if version_num is not None:
        v = db.query(ModelVersion).filter(ModelVersion.model_id == model.id, ModelVersion.version == version_num).first()
        if v is None:
            raise HTTPException(status_code=404, detail=f"Версия {version_num} не найдена")
        return v
    v = db.get(ModelVersion, model.active_version_id) if model.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    return v


def _model_summary(m: Model, db: Session) -> dict:
    version = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    metrics = (version.metrics or {}) if version else {}
    return {
        "id": m.id,
        "name": m.name,
        "task_type": m.task_type,
        "target_col": m.target_col,
        "status": m.status,
        "active_version": version.version if version else None,
        "threshold": m.threshold,
        "metrics": {k: metrics.get(k) for k in ("roc_auc", "pr_auc", "mae", "rmse", "r2", "coverage") if k in metrics},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _log_predictions(
    model: Model, version: ModelVersion, records: list[dict], results: list[dict], mode: str, api_key_id: int | None, latency_ms: int, db: Session
):
    from app.services.jsonsafe import json_safe

    dataset = db.get(Dataset, model.dataset_id)
    if dataset is None:
        return
    pii_map = {c["name"]: c["pii"] for c in (dataset.columns_meta or []) if c.get("pii")}
    rows = []
    for rec, res in zip(records, results, strict=False):
        masked = pii_service.mask_record(rec, pii_map) if pii_map else rec
        rows.append(
            PredictionLog(
                prediction_id=res.get("prediction_id"),
                model_id=model.id,
                version_id=version.id,
                api_key_id=api_key_id,
                mode=mode,
                entity_id=str(rec.get("entity_id"))[:120] if rec.get("entity_id") else None,
                input=json_safe(masked),
                output=json_safe(res),
                latency_ms=latency_ms,
            )
        )
    db.add_all(rows)
    db.commit()


@router.get("/models")
def list_models(principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    principal_obj, kind = principal
    q = db.query(Model)
    if kind == "key":
        model_ids = principal_obj.model_ids or []
        if "all" in model_ids:
            pass
        elif model_ids:
            q = q.filter(Model.id.in_(model_ids))
        else:
            q = q.filter(Model.user_id == principal_obj.user_id)
    else:
        if principal_obj.role != "admin":
            q = q.filter(Model.user_id == principal_obj.id)
    return [_model_summary(m, db) for m in q.order_by(Model.created_at.desc()).all()]


@router.get("/models/{model_id}/schema")
def model_schema(model_id: int, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, None, db)
    try:
        bundle = engine.load_bundle(v.id, v.dir_path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {**bundle["schema"], "model_version": v.version, "threshold": m.threshold}


@router.post("/models/{model_id}/predict")
def predict(model_id: int, body: PredictIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m, kind = _get_model(model_id, principal[0], principal[1], db), principal[1]
    v = _pick_version(m, body.version, db)
    try:
        bundle = engine.load_bundle(v.id, v.dir_path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None

    include = body.include or []
    if "actions" in include and len(body.data) > 10:
        raise HTTPException(
            status_code=422, detail="Рекомендация действия доступна не более чем для 10 записей за запрос — для пачки используйте плейбук (ACTIONS)"
        )
    threshold = m.threshold if m.task_type == "binary" else None

    start = time.monotonic()
    try:
        results, warnings = engine.predict_records(bundle, body.data, threshold=threshold, include_reasons="reasons" in include)
    except engine.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    latency_ms = int((time.monotonic() - start) * 1000)

    if "actions" in include and m.task_type == "binary" and m.actionable:
        for rec, res in zip(body.data, results, strict=False):
            cf = find_counterfactual(bundle, rec, m.actionable, threshold or 0.5, timeout=get_settings().cf_timeout_sec, cost_matrix=m.cost_matrix)
            if cf and not cf.get("already_ok"):
                res["recommended_action"] = {
                    "changes": cf["changes"],
                    "cost_rub": cf["cost_rub"],
                    "probability_after": cf["probability_after"],
                    "expected_roi_rub": cf.get("expected_roi_rub"),
                }
            else:
                res["recommended_action"] = None

    api_key_id = principal[0].id if kind == "key" else None
    mode = "api" if kind == "key" else "ui"
    _log_predictions(m, v, body.data, results, mode, api_key_id, latency_ms, db)
    PREDICT_REQUESTS.labels(str(model_id), mode).inc(len(results))
    PREDICT_LATENCY.labels(str(model_id)).observe(latency_ms / 1000)

    return {
        "model_id": m.id,
        "model_version": v.version,
        "predictions": results,
        "latency_ms": latency_ms,
        **({"warnings": warnings} if warnings else {}),
    }


@router.post("/models/{model_id}/predict/batch", status_code=202)
async def predict_batch(
    model_id: int,
    file: UploadFile = File(...),
    include: str = Form(""),
    version: int = Form(None),
    idempotency_key: str = Header(default=None, alias="Idempotency-Key"),
    principal=Depends(get_api_key_or_user),
    db: Session = Depends(get_db),
):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, version, db)
    settings = get_settings()
    suffix = Path(file.filename or "input.csv").suffix.lower()
    if suffix not in (".csv", ".xlsx", ".parquet"):
        raise HTTPException(status_code=422, detail="Файл должен быть CSV, XLSX или Parquet")
    tmp_dir = settings.storage_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    import secrets

    tmp_path = tmp_dir / f"batch_{secrets.token_hex(8)}{suffix}"
    with tmp_path.open("wb") as f:
        while chunk := file.file.read(1024 * 1024):
            f.write(chunk)
    includes = [s.strip() for s in include.split(",") if s.strip()]
    job = queue.create_job(
        "batch_predict",
        user_id=principal[0].id,
        model_id=m.id,
        dataset_id=m.dataset_id,
        payload={
            "input_path": str(tmp_path),
            "version_id": v.id,
            "include_reasons": "reasons" in includes,
            "threshold": m.threshold if m.task_type == "binary" else None,
        },
        idempotency_key=idempotency_key,
    )
    queue.submit(job)
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    out = {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress or {},
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if job.status == "done" and job.result_path:
        out["result_url"] = f"/api/v1/jobs/{job.id}/result/predictions.csv"
        out["result_url_xlsx"] = f"/api/v1/jobs/{job.id}/result/predictions.xlsx"
    return out


@router.get("/jobs/{job_id}/result/{filename}")
def job_result(job_id: str, filename: str, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None or not job.result_path:
        raise HTTPException(status_code=404, detail="Результат не найден")
    settings = get_settings()
    path = settings.storage_path / job.result_path / filename
    if not path.exists() or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path, filename=filename)


@router.post("/models/{model_id}/explain")
def explain(model_id: int, body: ExplainIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, body.version, db)
    bundle = engine.load_bundle(v.id, v.dir_path)
    try:
        results, warnings = engine.predict_records(bundle, [body.data], threshold=m.threshold, include_reasons=True)
    except engine.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    res = results[0]
    return {
        "model_id": m.id,
        "model_version": v.version,
        "prediction": res,
        **({"warnings": warnings} if warnings else {}),
    }


@router.post("/models/{model_id}/whatif")
def whatif(model_id: int, body: WhatIfIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, body.version, db)
    bundle = engine.load_bundle(v.id, v.dir_path)
    try:
        before, _ = engine.predict_records(bundle, [body.data], threshold=m.threshold)
        changed = {**body.data, **body.changes}
        after, _ = engine.predict_records(bundle, [changed], threshold=m.threshold)
    except engine.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {
        "model_id": m.id,
        "model_version": v.version,
        "before": before[0],
        "after": after[0],
        "caution": "Это ответ модели на изменение признака, а не доказанный причинный эффект",
    }


@router.post("/models/{model_id}/counterfactual")
def counterfactual(model_id: int, body: CounterfactualIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, body.version, db)
    if m.task_type != "binary":
        raise HTTPException(status_code=400, detail="Контрфактуалы поддерживаются для бинарной классификации")
    if not m.actionable:
        raise HTTPException(status_code=400, detail="Сначала разметьте управляемые признаки на вкладке ACTIONS")
    bundle = engine.load_bundle(v.id, v.dir_path)
    cf = find_counterfactual(
        bundle, body.data, m.actionable, m.threshold or 0.5, direction=body.direction, timeout=get_settings().cf_timeout_sec, cost_matrix=m.cost_matrix
    )
    if cf is None:
        return {"found": False, "detail": "Действие в заданных рамках не найдено"}
    return {
        "found": True,
        "changes": cf["changes"],
        "cost_rub": cf["cost_rub"],
        "probability_before": cf["probability_before"],
        "probability_after": cf["probability_after"],
        "expected_roi_rub": cf.get("expected_roi_rub"),
        "caution": "Контрфактуал — это ответ модели, а не доказанный причинный эффект",
    }


@router.post("/models/{model_id}/feedback", status_code=201)
def feedback(model_id: int, body: FeedbackIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    if body.actual is None or (not body.prediction_id and not body.entity_id):
        raise HTTPException(status_code=422, detail="Укажите actual и prediction_id или entity_id")
    actual = body.actual
    row = Feedback(model_id=m.id, prediction_id=body.prediction_id, entity_id=body.entity_id)
    if isinstance(actual, bool):
        row.actual_label = "1" if actual else "0"
    elif isinstance(actual, (int, float)):
        row.actual_numeric = float(actual)
    else:
        row.actual_label = str(actual)
    db.add(row)
    db.commit()
    return {"ok": True}


class PredictTsIn(BaseModel):
    history: list[float] = Field(min_length=35)
    horizon: int = Field(default=1, ge=1, le=30)


@router.post("/models/{model_id}/predict-ts")
def predict_ts(model_id: int, body: PredictTsIn, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = _pick_version(m, None, db)
    if m.task_type != "timeseries":
        raise HTTPException(status_code=400, detail="Модель не является прогнозом временного ряда")
    bundle = engine.load_bundle(v.id, v.dir_path)
    if bundle["pipeline"].get("kind") != "ts":
        raise HTTPException(status_code=400, detail="Артефакт не содержит временные компоненты")
    from app.core.training.ts import forecast_from_history

    try:
        forecast = forecast_from_history(bundle["pipeline"], body.history, body.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    conformal = bundle["conformal"]
    for f in forecast:
        lo, hi = None, None
        try:
            from app.core.uncertainty.conformal import regression_interval

            lo, hi = regression_interval(f["prediction"], conformal)
        except Exception:
            pass
        if lo is not None:
            f["interval_low"] = round(lo, 4)
            f["interval_high"] = round(hi, 4) if hi is not None else None
    return {"model_id": m.id, "model_version": v.version, "forecast": forecast}


@router.get("/models/{model_id}/versions")
def versions(model_id: int, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    return [
        {
            "version": v.version,
            "id": v.id,
            "status": v.status,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "active": v.id == m.active_version_id,
            "guard_verdict": (v.leakage_report or {}).get("verdict"),
        }
        for v in db.query(ModelVersion).filter(ModelVersion.model_id == m.id).order_by(ModelVersion.version).all()
    ]


@router.get("/models/{model_id}/card")
def model_card_v1(model_id: int, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    return {"card_md": v.card_md or "", "version": v.version, "llm_narrative": (v.metrics or {}).get("llm_narrative")}


@router.get("/models/{model_id}/monitor")
def monitor_v1(model_id: int, principal=Depends(get_api_key_or_user), db: Session = Depends(get_db)):
    m = _get_model(model_id, principal[0], principal[1], db)
    reports = db.query(DriftReport).filter(DriftReport.model_id == m.id).order_by(DriftReport.created_at.desc()).limit(10).all()
    return [
        {
            "id": r.id,
            "window_days": r.window_days,
            "status": r.status,
            "psi_prediction": r.psi_prediction,
            "top_psi": dict(sorted([(k, v) for k, v in (r.psi_features or {}).items() if v is not None], key=lambda kv: -kv[1])[:10]),
            "live_metrics": r.live_metrics,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]
