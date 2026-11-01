import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.jobs import queue
from app.models.database import Job, JobEvent, SessionLocal, User

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress or {},
        "error": job.error,
        "model_id": job.model_id,
        "dataset_id": job.dataset_id,
        "result_path": job.result_path,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/{job_id}")
def job_status(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return _job_out(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, user: User = Depends(get_current_user)):
    if not queue.request_cancel(job_id):
        raise HTTPException(status_code=400, detail="Задачу уже нельзя остановить")
    return {"ok": True}


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request, after: int = 0,
                     user: User = Depends(get_current_user)):
    db = SessionLocal()
    job = db.get(Job, job_id)
    db.close()
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    async def stream():
        last_id = after
        sent_done = False
        while True:
            if await request.is_disconnected():
                break
            s = SessionLocal()
            try:
                events = s.query(JobEvent).filter(JobEvent.job_id == job_id, JobEvent.id > last_id).order_by(JobEvent.id).all()
                current = s.get(Job, job_id)
                for ev in events:
                    last_id = ev.id
                    data = json.dumps({"data": ev.data, "ts": ev.ts.isoformat() if ev.ts else None}, ensure_ascii=False)
                    yield f"id: {ev.id}\nevent: {ev.type}\ndata: {data}\n\n"
                if current and current.status in ("done", "error", "cancelled"):
                    payload = {"status": current.status, "progress": current.progress or {}, "error": current.error,
                               "result_path": current.result_path}
                    yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    sent_done = True
            finally:
                s.close()
            if sent_done:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
