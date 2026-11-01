import pytest
from app.config import get_settings
from fastapi.testclient import TestClient

pytestmark = pytest.mark.ml


@pytest.fixture(scope="module")
def ml_client() -> TestClient:
    import os
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="pl-ml-"))
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
def ml_auth(ml_client: TestClient) -> TestClient:
    ml_client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    return ml_client


def _train_and_predict(csv_bytes: bytes, name: str, target: str, task: str, client: TestClient) -> dict:
    r = client.post("/api/datasets/upload", files={"file": (f"{name}.csv", csv_bytes, "text/csv")}, data={"name": name})
    assert r.status_code == 201, r.text[:300]
    ds_id = r.json()["id"]
    r = client.post("/api/models", json={"dataset_id": ds_id, "name": name, "target_col": target, "task_type": task})
    assert r.status_code == 201, r.text[:300]
    model = r.json()
    excluded = list(model.get("excluded_cols") or [])
    for c in (model.get("guard_report") or {}).get("exclude_auto", {}):
        excluded.append(c)
    id_cols = [c["name"] for c in client.get(f"/api/datasets/{ds_id}").json()["columns"] if c["type"] == "id"]
    client.patch(f"/api/models/{model['id']}", json={"excluded_cols": list(set(excluded + id_cols))})
    import time

    r = client.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
    assert r.status_code == 201, r.text[:200]
    job_id = r.json()["job_id"]
    for _ in range(300):
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(2)
    assert jr["status"] == "done", str(jr)[:300]
    model_detail = client.get(f"/api/models/{model['id']}").json()
    return model_detail


def test_b2b_leak_detection_then_honest(ml_auth: TestClient) -> None:
    from pathlib import Path

    csv_path = Path("demo-data/b2b_leaky.csv")
    if not csv_path.exists():
        pytest.skip("b2b_leaky.csv не найден")
    csv_bytes = csv_path.read_bytes()
    r = ml_auth.post("/api/datasets/upload", files={"file": ("leaky.csv", csv_bytes, "text/csv")}, data={"name": "leaky"})
    assert r.status_code == 201
    ds_id = r.json()["id"]
    r = ml_auth.post("/api/models", json={"dataset_id": ds_id, "name": "leak_test", "target_col": "churn", "task_type": "binary"})
    model = r.json()
    report = model.get("guard_report") or {}
    assert report.get("verdict") == "BLOCK", f"ожидался BLOCK, получен {report.get('verdict')}"
    details = " ".join(c["detail"] for c in report.get("checks", []))
    assert "cancel_date" in details
    assert "final_status" in details

    excluded = list(set(["cancel_date", "final_status", "customer_id"]))
    ml_auth.patch(f"/api/models/{model['id']}", json={"excluded_cols": excluded})
    ml_auth.post(f"/api/models/{model['id']}/recheck")
    import time

    r = ml_auth.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
    assert r.status_code == 201
    for _ in range(300):
        jr = ml_auth.get(f"/api/jobs/{r.json()['job_id']}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(2)
    assert jr["status"] == "done", str(jr)[:300]
    metrics = ml_auth.get(f"/api/models/{model['id']}").json().get("metrics") or {}
    auc = metrics.get("roc_auc")
    assert auc is not None and 0.5 < auc < 0.95, f"AUC {auc} вне честного диапазона"


def test_model_beats_baseline(ml_auth: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 3000
    signal = rng.normal(0, 1, n)
    df = pd.DataFrame(
        {"x1": signal, "x2": rng.normal(0, 1, n), "cat": rng.choice(["A", "B"], n), "target": (rng.random(n) < 1 / (1 + np.exp(-2 * signal))).astype(int)}
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    detail = _train_and_predict(buf.getvalue().encode(), "baseline_test", "target", "binary", ml_auth)
    metrics = detail.get("metrics") or {}
    auc = metrics.get("roc_auc")
    assert auc is not None and auc > 0.5, "модель должна быть лучше baseline (AUC > 0.5)"


def test_determinism(ml_auth: TestClient) -> None:
    import io
    import time

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(99)
    n = 2000
    df = pd.DataFrame(
        {
            "x1": rng.normal(0, 1, n),
            "target": (rng.random(n) < 1 / (1 + np.exp(-2 * df_x1))).astype(int) if (df_x1 := rng.normal(0, 1, n)) is not None else None,
        }
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    r = ml_auth.post("/api/datasets/upload", files={"file": ("det.csv", buf.getvalue().encode(), "text/csv")}, data={"name": "det"})
    ds_id = r.json()["id"]
    metrics_list = []
    for run in range(2):
        r = ml_auth.post("/api/models", json={"dataset_id": ds_id, "name": f"det_{run}", "target_col": "target", "task_type": "binary"})
        model = r.json()
        ml_auth.patch(f"/api/models/{model['id']}", json={"excluded_cols": []})
        jr2 = ml_auth.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
        assert jr2.status_code == 201
        for _ in range(300):
            jr = ml_auth.get(f"/api/jobs/{jr2.json()['job_id']}").json()
            if jr["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(2)
        assert jr["status"] == "done"
        m = ml_auth.get(f"/api/models/{model['id']}").json().get("metrics") or {}
        metrics_list.append(m)
    aucs = [m.get("roc_auc") for m in metrics_list if m.get("roc_auc") is not None]
    if len(aucs) == 2:
        assert abs(aucs[0] - aucs[1]) < 0.05, f"недетерминизм: {aucs[0]} vs {aucs[1]}"


def test_robustness_missing_and_unknown_categories(ml_auth: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 1000
    df = pd.DataFrame({"x1": rng.normal(0, 1, n), "cat": rng.choice(["A", "B"], n), "target": rng.integers(0, 2, n)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    detail = _train_and_predict(buf.getvalue().encode(), "robust_test", "target", "binary", ml_auth)
    mid = detail["id"]
    r = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": 0.5, "cat": "UNKNOWN"}]})
    assert r.status_code == 200, f"прогноз с незнакомой категорией не должен падать: {r.text[:200]}"
    r = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": 0.5, "cat": None}]})
    assert r.status_code == 200, "прогноз с пропуском не должен падать"


def test_serialization_consistency(ml_auth: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 500
    df = pd.DataFrame({"x1": rng.normal(0, 1, n), "target": (rng.random(n) < 1 / (1 + np.exp(-2 * rng.normal(0, 1, n)))).astype(int)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    detail = _train_and_predict(buf.getvalue().encode(), "ser_test", "target", "binary", ml_auth)
    mid = detail["id"]
    r1 = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": 0.5}]})
    r2 = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": 0.5}]})
    assert r1.status_code == 200 and r2.status_code == 200
    p1 = r1.json()["predictions"][0]["probability"]
    p2 = r2.json()["predictions"][0]["probability"]
    assert abs(p1 - p2) < 1e-12, "прогноз должен быть детерминированным"


def test_invariance_to_column_order(ml_auth: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 500
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    df = pd.DataFrame({"x1": x1, "x2": x2, "target": rng.integers(0, 2, n)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    detail = _train_and_predict(buf.getvalue().encode(), "inv_test", "target", "binary", ml_auth)
    mid = detail["id"]
    r1 = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x1": 0.5, "x2": 1.0}]})
    r2 = ml_auth.post(f"/api/v1/models/{mid}/predict", json={"data": [{"x2": 1.0, "x1": 0.5}]})
    p1 = r1.json()["predictions"][0]["probability"]
    p2 = r2.json()["predictions"][0]["probability"]
    assert abs(p1 - p2) < 1e-12, "порядок полей не должен менять прогноз"


def test_calibration_brier_improves(ml_auth: TestClient) -> None:
    import io

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 2000
    x = rng.normal(0, 1, n)
    df = pd.DataFrame({"x1": x, "x2": rng.normal(0, 1, n), "target": (rng.random(n) < 1 / (1 + np.exp(-1.5 * x))).astype(int)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    detail = _train_and_predict(buf.getvalue().encode(), "cal_test", "target", "binary", ml_auth)
    metrics = detail.get("metrics") or {}
    brier = metrics.get("brier")
    assert brier is not None and brier < 0.25, f"Brier score {brier} слишком высок"
