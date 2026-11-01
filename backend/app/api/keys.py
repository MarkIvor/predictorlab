from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.models.database import ApiKey, Model, User, utcnow
from app.services import security

router = APIRouter(prefix="/api/keys", tags=["keys"])


class KeyCreateIn(BaseModel):
    name: str = ""
    model_ids: list[int] = Field(default_factory=list)
    all_models: bool = False
    rate_limit_rpm: int = 0


class KeyPatchIn(BaseModel):
    name: str | None = None
    model_ids: list[int] | None = None
    rate_limit_rpm: int | None = None


def _key_out(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix + "…",
        "model_ids": k.model_ids or [],
        "all_models": "all" in (k.model_ids or []),
        "rate_limit_rpm": k.rate_limit_rpm,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
    }


def _own_keys(db: Session, user: User):
    q = db.query(ApiKey).filter(ApiKey.user_id == user.id)
    if user.role == "admin":
        q = db.query(ApiKey)
    return q.order_by(ApiKey.id.desc()).all()


def _validate_model_ids(db: Session, user: User, model_ids: list[int]):
    if user.role == "admin":
        return
    own = {m.id for m in db.query(Model.id).filter(Model.user_id == user.id).all()}
    for mid in model_ids:
        if mid not in own:
            raise HTTPException(status_code=403, detail="Модель не найдена или недоступна")


@router.get("")
def list_keys(user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    return [_key_out(k) for k in _own_keys(db, user)]


@router.post("", status_code=201)
def create_key(body: KeyCreateIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    model_ids = ["all"] if (body.all_models and user.role == "admin") else list(body.model_ids)
    _validate_model_ids(db, user, [m for m in model_ids if m != "all"])
    key, key_hash, prefix = security.generate_api_key()
    k = ApiKey(
        user_id=user.id,
        name=body.name or "Ключ",
        key_hash=key_hash,
        prefix=prefix,
        model_ids=model_ids,
        rate_limit_rpm=max(0, body.rate_limit_rpm),
    )
    db.add(k)
    db.commit()
    return {**_key_out(k), "key": key, "note": "Ключ показывается только один раз — сохраните его"}


@router.patch("/{key_id}")
def patch_key(key_id: int, body: KeyPatchIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if k is None or (k.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Ключ не найден")
    if body.name is not None:
        k.name = body.name
    if body.model_ids is not None:
        _validate_model_ids(db, user, [m for m in body.model_ids if m != "all"])
        k.model_ids = list(body.model_ids)
    if body.rate_limit_rpm is not None:
        k.rate_limit_rpm = max(0, body.rate_limit_rpm)
    db.commit()
    return _key_out(k)


@router.post("/{key_id}/revoke")
def revoke_key(key_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if k is None or (k.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Ключ не найден")
    k.revoked_at = utcnow()
    db.commit()
    return _key_out(k)
