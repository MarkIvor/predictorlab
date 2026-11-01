import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db, require_role
from app.config import get_settings
from app.core.predict import engine
from app.models.database import Model, ModelVersion, PredictionLog, User
from app.services import rate_limiter
from app.services.metrics import PREDICT_REQUESTS

router = APIRouter(prefix="/api/public", tags=["public"])

SLUG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class PublicManageIn(BaseModel):
    enabled: bool
    slug: str | None = None
    password: str | None = None


class PublicPredictIn(BaseModel):
    data: dict
    password: str | None = None


def _public_model(slug: str, db: Session) -> tuple[Model, ModelVersion]:
    m = db.query(Model).filter(Model.slug == slug).first()
    if m is None or not m.slug:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    return m, v


@router.post("/manage/{model_id}", status_code=201)
def manage_public(model_id: int, body: PublicManageIn,
                  user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = db.get(Model, model_id)
    if m is None or (user.role != "admin" and m.user_id != user.id):
        raise HTTPException(status_code=404, detail="Модель не найдена")
    settings = get_settings()
    if not body.enabled:
        m.slug = None
        m.public_password_hash = None
        db.commit()
        return {"enabled": False, "url": None}
    slug = (body.slug or "").strip().lower().replace(" ", "-") or "".join(secrets.choice(SLUG_ALPHABET) for _ in range(8))
    if not all(ch in SLUG_ALPHABET + "-" for ch in slug) or not (1 <= len(slug) <= 40):
        raise HTTPException(status_code=422, detail="Slug: латиница, цифры и дефис, до 40 символов")
    exists = db.query(Model).filter(Model.slug == slug, Model.id != m.id).first()
    if exists:
        raise HTTPException(status_code=409, detail="Такой slug уже занят")
    from app.services.security import hash_password
    m.slug = slug
    if body.password:
        m.public_password_hash = hash_password(body.password)
    db.commit()
    return {"enabled": True, "url": f"{settings.public_base_url}/p/{slug}", "has_password": bool(m.public_password_hash)}


@router.get("/p/{slug}")
def public_info(slug: str, db: Session = Depends(get_db)):
    m, v = _public_model(slug, db)
    bundle = engine.load_bundle(v.id, v.dir_path)
    return {
        "name": m.name,
        "task_type": m.task_type,
        "model_version": v.version,
        "has_password": bool(m.public_password_hash),
        "input_schema": bundle["schema"]["input_schema"],
        "example": bundle["schema"].get("example"),
    }


@router.post("/p/{slug}/predict")
def public_predict(slug: str, body: PublicPredictIn, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    ip = client_ip(request)
    m, v = _public_model(slug, db)
    if not rate_limiter.allow(f"pub:{m.id}:{ip}", settings.public_rate_limit_rpm):
        raise HTTPException(status_code=429, detail="Слишком много запросов с этого адреса — подождите минуту")
    if m.public_password_hash:
        from app.services.security import verify_password
        if not body.password or not verify_password(body.password, m.public_password_hash):
            raise HTTPException(status_code=401, detail="Неверный пароль страницы")
    bundle = engine.load_bundle(v.id, v.dir_path)
    try:
        results, warnings = engine.predict_records(
            bundle, [body.data],
            threshold=m.threshold if m.task_type == "binary" else None,
            include_reasons=True)
    except engine.ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    res = results[0]
    db.add(PredictionLog(prediction_id=res["prediction_id"], model_id=m.id, version_id=v.id,
                         mode="public", input=body.data, output=res, latency_ms=0))
    db.commit()
    PREDICT_REQUESTS.labels(str(m.id), "public").inc()
    return {"prediction": res, "warnings": warnings[:3]}
