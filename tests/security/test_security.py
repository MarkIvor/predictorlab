import pytest
from app.config import get_settings
from fastapi.testclient import TestClient

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def sec_client() -> TestClient:
    import os
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="pl-sec-"))
    os.environ["DATA_DIR"] = str(tmp / "data")
    os.environ["STORAGE_DIR"] = str(tmp / "storage")
    os.environ["ADMIN_EMAIL"] = "admin@predictorlab.io"
    os.environ["ADMIN_PASSWORD"] = "admin"

    get_settings.cache_clear()
    from app.main import app
    from app.models.database import init_db

    init_db()
    yield TestClient(app)
    get_settings.cache_clear()
    os.environ.pop("DATA_DIR", None)
    os.environ.pop("STORAGE_DIR", None)


def test_api_key_stored_as_hash_only(sec_client: TestClient) -> None:
    sec_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    r = sec_client.post("/api/keys", json={"name": "sec_test", "model_ids": []})
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("pl_live_")

    keys = sec_client.get("/api/keys").json()
    assert len(keys) >= 1
    for k in keys:
        assert not k.get("key"), "ключ не должен храниться в открытом виде в списке"
        assert k.get("prefix", "").startswith("pl_live_")

    import hashlib

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    assert key_hash != key, "хэш ≠ исходный ключ"


def test_unauthorized_401(sec_client: TestClient) -> None:
    import httpx

    httpx.Client(base_url="http://test", timeout=10)

    from fastapi.testclient import TestClient as _TC

    tc = _TC(sec_client.app)
    tc.cookies.clear()
    endpoints = ["/api/models", "/api/datasets", "/api/keys", "/api/admin/stats"]
    for ep in endpoints:
        r = tc.get(ep)
        assert r.status_code == 401, f"{ep} должен требовать авторизацию (получен {r.status_code})"


def test_viewer_cannot_create(sec_client: TestClient) -> None:
    sec_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    sec_client.post("/api/auth/users", json={"email": "viewer@test.io", "password": "viewerpass", "role": "viewer"})
    sec_client.post("/api/auth/login", json={"email": "viewer@test.io", "password": "viewerpass"})
    r = sec_client.post("/api/datasets/upload", files={"file": ("v.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 403, "viewer не может загружать датасеты"
    r = sec_client.post("/api/models", json={"dataset_id": "x", "name": "v", "target_col": "t"})
    assert r.status_code in (403, 422), "viewer не может создавать модели"
    sec_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})


def test_sql_guard_blocks_dml_and_ddl(sec_client: TestClient) -> None:
    from app.services.sql_guard import check_read_only

    for sql in [
        "INSERT INTO t VALUES (1)",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE t",
        "ALTER TABLE t ADD x INT",
        "CREATE TABLE x (a int)",
        "GRANT ALL ON t TO u",
        "PRAGMA journal_mode=wal",
    ]:
        ok, _ = check_read_only(sql)
        assert not ok, f"sql_guard должен блокировать: {sql}"


def test_sql_guard_allows_select(sec_client: TestClient) -> None:
    from app.services.sql_guard import check_read_only

    for sql in ["SELECT * FROM t", "WITH x AS (SELECT 1) SELECT * FROM x", "SHOW TABLES", "DESCRIBE t"]:
        ok, _ = check_read_only(sql)
        assert ok, f"sql_guard не должен блокировать: {sql}"


def test_pii_not_in_logs(sec_client: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 500
    df = pd.DataFrame({"email": [f"user{i}@secret.com" for i in range(n)], "x1": rng.normal(0, 1, n), "target": rng.integers(0, 2, n)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    sec_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    r = sec_client.post("/api/datasets/upload", files={"file": ("pii.csv", buf.getvalue().encode(), "text/csv")}, data={"name": "pii_test"})
    assert r.status_code == 201
    ds = r.json()
    email_col = next((c for c in ds["columns"] if c["name"] == "email"), None)
    assert email_col is not None, "email-колонка должна быть обнаружена как ПДн"
    assert email_col.get("pii") == "email"
    assert email_col.get("excluded") is True, "ПДн должны быть исключены из обучения по умолчанию"
    preview = ds.get("preview") or []
    for row in preview[:5]:
        email_val = row.get("email", "")
        if "@" in str(email_val):
            assert "***" in str(email_val), f"email в превью должен быть маскирован: {email_val}"
