from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.models.database import ApiKey, Dataset, Model, PredictionLog, User, Webhook, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LlmSettingsIn(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""


class WebhookIn(BaseModel):
    url: str
    model_id: int | None = None
    events: list[str] = ["drift", "live_metric_drop"]


@router.get("/stats")
def stats(admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    day_ago = utcnow() - timedelta(days=1)
    predictions_24h = db.query(func.count(PredictionLog.id)).filter(PredictionLog.created_at >= day_ago).scalar() or 0
    avg_latency = db.query(func.avg(PredictionLog.latency_ms)).filter(PredictionLog.created_at >= day_ago, PredictionLog.latency_ms > 0).scalar()
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "models": db.query(func.count(Model.id)).scalar(),
        "ready_models": db.query(func.count(Model.id)).filter(Model.status == "ready").scalar(),
        "datasets": db.query(func.count(Dataset.id)).scalar(),
        "api_keys": db.query(func.count(ApiKey.id)).scalar(),
        "predictions_24h": predictions_24h,
        "avg_latency_ms": round(avg_latency or 0),
    }


@router.get("/llm")
def get_llm(admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    from app.llm.client import llm_config

    cfg = llm_config()
    return {
        "enabled": cfg["enabled"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_masked": (cfg["api_key"][:6] + "…") if cfg["api_key"] else "",
    }


@router.put("/llm")
def put_llm(body: LlmSettingsIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    from app.models.database import AppSetting

    row = db.get(AppSetting, "llm")
    value = dict(row.value) if row and row.value else {}
    if body.base_url is not None:
        value["base_url"] = body.base_url
    if body.model:
        value["model"] = body.model
    if body.api_key:
        value["api_key"] = body.api_key
    if row is None:
        row = AppSetting(key="llm", value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    from app.llm.client import llm_config

    cfg = llm_config()
    return {"enabled": cfg["enabled"], "base_url": cfg["base_url"], "model": cfg["model"]}


@router.get("/webhooks")
def list_webhooks(admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [
        {"id": w.id, "url": w.url, "model_id": w.model_id, "events": w.events, "active": w.active} for w in db.query(Webhook).order_by(Webhook.id.desc()).all()
    ]


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if not body.url.startswith("http"):
        raise HTTPException(status_code=422, detail="URL вебхука должен начинаться с http")
    w = Webhook(url=body.url, model_id=body.model_id, events=body.events)
    db.add(w)
    db.commit()
    return {"id": w.id}


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    w = db.get(Webhook, webhook_id)
    if w is None:
        raise HTTPException(status_code=404, detail="Вебхук не найден")
    db.delete(w)
    db.commit()
    return {"ok": True}
