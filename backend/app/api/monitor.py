import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import get_settings
from app.jobs import queue
from app.models.database import DriftReport, Feedback, Model, PredictionLog, SessionLocal, User, utcnow

logger = logging.getLogger("predictorlab.monitor")

router = APIRouter(prefix="/api/models", tags=["monitor"])


class FeedbackUIIn(BaseModel):
    prediction_id: str | None = None
    entity_id: str | None = None
    actual: object = None


def _owned_model(model_id: int, user: User, db: Session) -> Model:
    m = db.get(Model, model_id)
    if m is None or (user.role != "admin" and m.user_id != user.id):
        raise HTTPException(status_code=404, detail="Модель не найдена")
    return m


@router.post("/{model_id}/monitor/run", status_code=202)
def run_monitor(model_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = _owned_model(model_id, user, db)
    if not m.active_version_id:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    job = queue.create_job("drift", user_id=user.id, model_id=m.id, payload={"version_id": m.active_version_id, "window_days": 30})
    queue.submit(job)
    return {"job_id": job.id}


@router.get("/{model_id}/monitor")
def monitor(model_id: int, user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = _owned_model(model_id, user, db)
    reports = db.query(DriftReport).filter(DriftReport.model_id == m.id).order_by(DriftReport.created_at.desc()).limit(20).all()
    return [
        {
            "id": r.id,
            "window_days": r.window_days,
            "status": r.status,
            "psi_prediction": r.psi_prediction,
            "top_psi": dict(sorted([(k, v) for k, v in (r.psi_features or {}).items() if v is not None], key=lambda kv: -kv[1])[:10]),
            "live_metrics": r.live_metrics,
            "report": r.report,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]


@router.get("/{model_id}/predictions")
def recent_predictions(model_id: int, limit: int = 50, user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = _owned_model(model_id, user, db)
    rows = db.query(PredictionLog).filter(PredictionLog.model_id == m.id).order_by(PredictionLog.created_at.desc()).limit(max(1, min(limit, 500))).all()
    return [
        {
            "prediction_id": p.prediction_id,
            "mode": p.mode,
            "entity_id": p.entity_id,
            "input": p.input,
            "output": p.output,
            "latency_ms": p.latency_ms,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@router.post("/{model_id}/feedback", status_code=201)
def add_feedback(model_id: int, body: FeedbackUIIn, user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = _owned_model(model_id, user, db)
    if body.actual is None or (not body.prediction_id and not body.entity_id):
        raise HTTPException(status_code=422, detail="Укажите actual и prediction_id или entity_id")
    row = Feedback(model_id=m.id, prediction_id=body.prediction_id, entity_id=body.entity_id)
    actual = body.actual
    if isinstance(actual, bool):
        row.actual_label = "1" if actual else "0"
    elif isinstance(actual, (int, float)):
        row.actual_numeric = float(actual)
    else:
        row.actual_label = str(actual)
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("/{model_id}/playbook", status_code=202)
async def run_playbook(model_id: int, file: UploadFile, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    import secrets
    from pathlib import Path

    m = _owned_model(model_id, user, db)
    if not m.active_version_id:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    if m.task_type != "binary":
        raise HTTPException(status_code=400, detail="Плейбук работает с бинарной классификацией")
    if not m.actionable:
        raise HTTPException(status_code=400, detail="Сначала разметьте управляемые признаки на вкладке ACTIONS")
    settings = get_settings()
    suffix = Path(file.filename or "input.csv").suffix.lower()
    if suffix not in (".csv", ".xlsx", ".parquet"):
        raise HTTPException(status_code=422, detail="Файл должен быть CSV, XLSX или Parquet")
    tmp_dir = settings.storage_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"playbook_{secrets.token_hex(8)}{suffix}"
    with tmp_path.open("wb") as f:
        while chunk := file.file.read(1024 * 1024):
            f.write(chunk)
    job = queue.create_job("playbook", user_id=user.id, model_id=m.id, payload={"input_path": str(tmp_path), "version_id": m.active_version_id})
    queue.submit(job)
    return {"job_id": job.id}


async def ttl_cleanup_loop():
    settings = get_settings()
    while True:
        try:
            await asyncio.sleep(3600)
            db = SessionLocal()
            try:
                cutoff = utcnow() - timedelta(days=settings.prediction_log_ttl_days)
                deleted = db.query(PredictionLog).filter(PredictionLog.created_at < cutoff).delete()
                db.commit()
                if deleted:
                    logger.info("prediction log TTL cleanup: %s rows", deleted)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("ttl cleanup failed")


async def schedule_loop():
    settings = get_settings()
    while True:
        try:
            await asyncio.sleep(settings.retrain_check_minutes * 60)
            db = SessionLocal()
            try:
                models = db.query(Model).filter(Model.schedule.isnot(None)).all()
                for m in models:
                    schedule = m.schedule or {}
                    if not schedule.get("enabled") or not m.active_version_id:
                        continue
                    interval_days = float(schedule.get("interval_days", 30))
                    last = schedule.get("last_run")
                    if last:
                        from datetime import datetime

                        try:
                            last_dt = datetime.fromisoformat(last)
                        except ValueError:
                            last_dt = None
                        if last_dt and (utcnow() - last_dt).days < interval_days:
                            continue
                    job = queue.create_job(
                        "train", user_id=m.user_id, model_id=m.id, dataset_id=m.dataset_id, payload={"mode": schedule.get("mode", "quick"), "scheduled": True}
                    )
                    queue.submit(job)
                    schedule["last_run"] = utcnow().isoformat()
                    m.schedule = schedule
                    db.commit()
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("retrain schedule failed")
