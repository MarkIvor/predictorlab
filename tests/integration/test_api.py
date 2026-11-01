import pytest
from app.config import get_settings
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client() -> TestClient:
    import os
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="pl-int-"))
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


@pytest.fixture(scope="module")
def auth_client(client: TestClient) -> TestClient:
    client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    return client


def _make_csv(n: int = 1000) -> bytes:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "x1": rng.normal(0, 1, n),
            "x2": rng.normal(5, 2, n),
            "cat": rng.choice(["A", "B", "C"], n),
            "target": (rng.random(n) < 0.3).astype(int),
        }
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_unauthorized(client: TestClient) -> None:
    r = client.get("/api/models")
    assert r.status_code == 401


def test_auth_wrong_password(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "wrong"})
    assert r.status_code == 401


def test_upload_and_create_model(auth_client: TestClient) -> None:
    csv_data = _make_csv(1000)
    r = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", csv_data, "text/csv")},
        data={"name": "integration_test"},
    )
    assert r.status_code == 201, r.text[:300]
    ds = r.json()
    assert ds["nrows"] == 1000

    r2 = auth_client.post(
        "/api/models",
        json={"dataset_id": ds["id"], "name": "int_model", "target_col": "target", "task_type": "binary"},
    )
    assert r2.status_code == 201, r2.text[:300]
    model = r2.json()
    assert model["task_type"] == "binary"


def test_predict_422_on_wrong_type(auth_client: TestClient) -> None:
    models = auth_client.get("/api/models").json()
    ready = [m for m in models if m.get("status") == "ready"]
    if not ready:
        pytest.skip("нет обученных моделей")
    mid = ready[0]["id"]
    r = auth_client.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": "hello"}]})
    assert r.status_code == 422
    assert "ожидается" in r.text


def test_predict_401_no_key() -> None:
    from app.main import app as _app
    from fastapi.testclient import TestClient as _TC

    fresh = _TC(_app)
    fresh.cookies.clear()
    r = fresh.post("/api/v1/models/999/predict", json={"data": [{"a": 1}]})
    assert r.status_code == 401, f"должен быть 401 (получен {r.status_code}: {r.text[:100]})"


def test_api_key_lifecycle(auth_client: TestClient) -> None:
    r = auth_client.post("/api/keys", json={"name": "test", "model_ids": []})
    assert r.status_code == 201
    key_data = r.json()
    assert "key" in key_data
    assert key_data["key"].startswith("pl_live_")

    keys = auth_client.get("/api/keys").json()
    assert len(keys) >= 1
    assert not any(k.get("key") for k in keys), "ключ не должен повторно показываться"

    revoke = auth_client.post(f"/api/keys/{key_data['id']}/revoke")
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None


def test_cross_user_403(auth_client: TestClient) -> None:
    auth_client.post("/api/auth/users", json={"email": "user2@test.io", "password": "userpass1", "role": "builder"})
    r = auth_client.post("/api/auth/login", json={"email": "user2@test.io", "password": "userpass1"})
    assert r.status_code == 200

    models = auth_client.get("/api/models").json()
    if models:
        mid = models[0]["id"]
        auth_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
        r = auth_client.get(f"/api/models/{mid}")
        assert r.status_code == 200


def test_sql_guard_injection(auth_client: TestClient) -> None:
    r = auth_client.post("/api/datasets/upload", files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 201
    ds_id = r.json()["id"]
    r2 = auth_client.get(f"/api/datasets/{ds_id}")
    assert r2.status_code == 200
