import asyncio
import importlib
import logging
from concurrent.futures import ProcessPoolExecutor

from app.models.database import Job, SessionLocal, utcnow
from app.services.ids import new_id

logger = logging.getLogger("predictorlab.jobs")

ENTRYPOINTS = {
    "train": "app.core.training.runner:run",
    "features_build": "app.core.features.builder:run",
    "batch_predict": "app.core.predict.batch:run",
    "playbook": "app.core.business.playbook:run",
    "drift": "app.core.monitor.jobs:run",
}

_pool: ProcessPoolExecutor | None = None
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop


def pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2)
    return _pool


def shutdown_pool():
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def resolve_entry(entry: str):
    module, func = entry.split(":")
    mod = importlib.import_module(module)
    return getattr(mod, func)


def create_job(job_type: str, user_id: int | None = None, model_id: int | None = None,
               dataset_id: int | None = None, payload: dict | None = None,
               idempotency_key: str | None = None) -> Job:
    if job_type not in ENTRYPOINTS:
        raise ValueError(f"Unknown job type: {job_type}")
    db = SessionLocal()
    try:
        if idempotency_key:
            existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
            if existing:
                return existing
        job = Job(
            id=new_id("job"),
            type=job_type,
            user_id=user_id,
            model_id=model_id,
            dataset_id=dataset_id,
            payload=payload or {},
            status="queued",
        )
        if idempotency_key:
            job.idempotency_key = idempotency_key
        db.add(job)
        db.commit()
        return job
    finally:
        db.close()


def submit(job: Job) -> Job:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_job(job.id, ENTRYPOINTS[job.type]))
    except RuntimeError:
        if _main_loop is None or _main_loop.is_closed():
            raise RuntimeError("Нет активного event loop для фоновой задачи")
        _main_loop.call_soon_threadsafe(
            lambda: _main_loop.create_task(_run_job(job.id, ENTRYPOINTS[job.type])))
    return job


async def _run_job(job_id: str, entry: str):
    loop = asyncio.get_running_loop()
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job.status in ("done", "error", "cancelled"):
            return
        job.status = "running"
        job.started_at = utcnow()
        db.commit()
    finally:
        db.close()
    try:
        fn = resolve_entry(entry)
        result = await loop.run_in_executor(pool(), fn, job_id)
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job.status == "cancelled":
                return
            job.status = "done"
            job.finished_at = utcnow()
            if isinstance(result, dict):
                job.progress = {**(job.progress or {}), **result}
                if "result_path" in result:
                    job.result_path = result["result_path"]
            db.commit()
        finally:
            db.close()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job and job.status != "cancelled":
                if job.cancel_requested:
                    job.status = "cancelled"
                else:
                    job.status = "error"
                    job.error = str(exc)[:4000]
                job.finished_at = utcnow()
                db.commit()
        finally:
            db.close()


def request_cancel(job_id: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status not in ("queued", "running"):
            return False
        job.cancel_requested = True
        db.commit()
        return True
    finally:
        db.close()


def is_cancel_requested(job_id: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        return bool(job and job.cancel_requested)
    finally:
        db.close()
