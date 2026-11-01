from fastapi import Depends, HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.database import ApiKey, SessionLocal, User, utcnow
from app.services import rate_limiter, security


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_from_jwt(db: Session, token: str) -> User | None:
    payload = security.decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("authorization", "")
        scheme, param = get_authorization_scheme_param(header)
        if scheme.lower() == "bearer" and param and not param.startswith("pl_live_"):
            token = param
    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход в систему")
    user = _user_from_jwt(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав для этого действия")
        return user

    return dep


def get_api_key_or_user(request: Request, db: Session = Depends(get_db)) -> tuple[object, str]:
    header = request.headers.get("authorization", "")
    scheme, param = get_authorization_scheme_param(header)
    if scheme.lower() == "bearer" and param.startswith("pl_live_"):
        key_hash = security.sha256_hex(param)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if api_key is None or api_key.revoked_at is not None:
            raise HTTPException(status_code=401, detail="API-ключ недействителен или отозван")
        settings = get_settings()
        limit = api_key.rate_limit_rpm or settings.global_rate_limit_rpm
        if not rate_limiter.allow(f"key:{api_key.id}", limit):
            raise HTTPException(status_code=429, detail="Превышен лимит запросов для ключа, попробуйте позже")
        api_key.last_used_at = utcnow()
        db.commit()
        return api_key, "key"
    token = request.cookies.get("access_token") or (param if param else None)
    if token:
        user = _user_from_jwt(db, token)
        if user:
            if not rate_limiter.allow(f"jwt:{user.id}", get_settings().global_rate_limit_rpm):
                raise HTTPException(status_code=429, detail="Превышен лимит запросов, попробуйте позже")
            return user, "jwt"
    raise HTTPException(status_code=401, detail="Нужен API-ключ (Bearer pl_live_…) или вход в систему")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_model_access(principal, kind: str, model_owner_id: int, model_id: int) -> None:
    if kind != "key":
        return
    model_ids = principal.model_ids or []
    if "all" in model_ids:
        return
    if model_ids:
        if model_id in model_ids:
            return
    elif principal.user_id == model_owner_id:
        return
    raise HTTPException(status_code=403, detail="Ключ не имеет доступа к этой модели")
