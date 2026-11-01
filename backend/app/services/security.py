import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(password, hashed)
    except Exception:
        return False


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jwt_secret() -> str:
    s = get_settings()
    if s.jwt_secret:
        return s.jwt_secret
    secret_file = s.data_path / "jwt.secret"
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(secret, encoding="utf-8")
    return secret


def create_token(user_id: int, role: str, token_type: str = "access") -> str:
    ttl = 30 if token_type == "access" else 60 * 24 * 7
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "exp": datetime.now(UTC) + timedelta(minutes=ttl),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except Exception:
        return None


def generate_api_key() -> tuple[str, str, str]:
    key = "pl_live_" + secrets.token_urlsafe(32)
    return key, sha256_hex(key), key[:16]


def _fernet() -> Fernet:
    s = get_settings()
    seed = s.encryption_key or s.jwt_secret or _jwt_secret()
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
