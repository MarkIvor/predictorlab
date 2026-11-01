from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.models.database import User
from app.services import security

router = APIRouter(prefix="/api/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _set_cookies(response: Response, user: User):
    access = security.create_token(user.id, user.role, "access")
    refresh = security.create_token(user.id, user.role, "refresh")
    response.set_cookie(ACCESS_COOKIE, access, httponly=True, samesite="lax", max_age=1800, path="/")
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, samesite="lax", max_age=604800, path="/")
    return access, refresh


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    must_change_password: bool

    model_config = {"from_attributes": True}


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = ""
    role: str = Field(default="viewer", pattern="^(admin|builder|viewer)$")


class UserPatchIn(BaseModel):
    display_name: str | None = None
    role: str | None = Field(default=None, pattern="^(admin|builder|viewer)$")
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=8)


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        must_change_password=u.must_change_password,
    )


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена администратором")
    _set_cookies(response, user)
    return {"user": user_out(user)}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not security.verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
    user.password_hash = security.hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    _set_cookies(response, user)
    return {"ok": True, "user": user_out(user)}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново")
    payload = security.decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново")
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Учётная запись недоступна")
    _set_cookies(response, user)
    return {"user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"ok": True}


@router.get("/users")
def list_users(admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users", status_code=201)
def create_user(body: UserCreateIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == body.email.lower()).first()
    if exists:
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    u = User(
        email=body.email.lower(),
        password_hash=security.hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
        role=body.role,
        must_change_password=True,
    )
    db.add(u)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatchIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if body.display_name is not None:
        u.display_name = body.display_name
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.new_password:
        u.password_hash = security.hash_password(body.new_password)
        u.must_change_password = True
    db.commit()
    return user_out(u)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственную учётную запись")
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    u.is_active = False
    db.commit()
    return {"ok": True}
