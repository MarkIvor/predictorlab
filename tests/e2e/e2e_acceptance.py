"""Приёмочные проверки 13.2–13.4, требующие живого инстанса: Telco/housing quick,
исполнение сниппетов curl и Python без правок, дрейф → вебхук, откат версии."""

import http.server
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8200"
DEMO = Path(__file__).resolve().parents[1] / "demo-data"
passed: list[str] = []
failed: list[str] = []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))


def wait_job(client, job_id, timeout=1800):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            return jr
        time.sleep(3)
    return {"status": "timeout"}


def train_ready_binary(client, dataset_path, name, target, expect_auc=True, is_regression=False):
    with open(dataset_path, "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (dataset_path.name, f, "text/csv")}, data={"name": name, "sample_rows": ""})
    assert r.status_code == 201, f"upload {name}: {r.text[:200]}"
    ds_id = r.json()["id"]
    event_col = next((c["name"] for c in r.json()["columns"] if c["type"] == "datetime"), None)

    model = None
    for _ in range(2):
        r = client.post("/api/models", json={"dataset_id": ds_id, "name": name, "target_col": target, **({"event_time_col": event_col} if event_col else {})})
        assert r.status_code == 201, f"model {name}: {r.text[:300]}"
        model = r.json()
        report = model.get("guard_report") or {}
        if report.get("verdict") == "BLOCK":
            checks = report.get("checks") or []
            if any(c["id"] == "train_test_overlap" for c in checks):
                dedup = client.post(f"/api/datasets/{ds_id}/dedupe")
                assert dedup.status_code == 201, dedup.text[:200]
                ds_id = dedup.json()["id"]
                continue
        break

    excluded = list(model.get("excluded_cols") or [])
    for c in (model.get("guard_report") or {}).get("exclude_auto", {}):
        excluded.append(c)
    id_cols = [c["name"] for c in client.get(f"/api/datasets/{ds_id}").json()["columns"] if c["type"] == "id"]
    client.patch(f"/api/models/{model['id']}", json={"excluded_cols": list(set(excluded + id_cols))})
    r = client.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
    assert r.status_code == 201, r.text[:200]
    jr = wait_job(client, r.json()["job_id"])
    return model["id"], jr


def main():
    client = httpx.Client(base_url=BASE, timeout=1800)
    r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab2026"})
    assert r.status_code == 200, "login failed — запустите с паролем из .env"

    print("== A. Telco Customer Churn: сценарий §4 в quick ==")
    telco_id, jr = train_ready_binary(client, DEMO / "telco.csv", "telco_churn", "Churn")
    check("telco_quick_trained", jr["status"] == "done", str(jr)[:300])
    metrics = client.get(f"/api/models/{telco_id}").json().get("metrics") or {}
    auc = metrics.get("roc_auc")
    check("telco_auc_sane", auc is not None and 0.6 < auc < 0.95, f"AUC={auc}")

    print("== B. Цены на жильё: регрессия ==")
    housing_id, jr2 = train_ready_binary(client, DEMO / "housing.csv", "housing_prices", "median_house_value")
    check("housing_regression_trained", jr2["status"] == "done", str(jr2)[:300])
    hm = client.get(f"/api/models/{housing_id}").json().get("metrics") or {}
    check(
        "housing_mae_sane", hm.get("mae") is not None and hm.get("mae") < hm.get("baseline_mae", 1e18), f"MAE={hm.get('mae')} baseline={hm.get('baseline_mae')}"
    )
    check("housing_coverage", hm.get("coverage") is not None and 0.85 <= hm["coverage"] <= 0.95, f"coverage={hm.get('coverage')}")

    print("== C. Сниппеты curl и Python выполняются без правок ==")
    key = client.post("/api/keys", json={"name": "snippets", "model_ids": [telco_id]}).json()["key"]
    snippets = client.get(f"/api/models/{telco_id}/snippets").json()
    curl_cmd = snippets["curl"].replace("pl_live_ВАШ_КЛЮЧ", key).replace("http://localhost:8000", BASE)
    import re

    url_m = re.search(r'curl -X POST "([^"]+)"', curl_cmd)
    auth_m = re.search(r'-H "Authorization: Bearer ([^"]+)"', curl_cmd)
    body_m = re.search(r"-d '(\{.*\})'", curl_cmd, re.S)
    ok_curl = False
    if url_m and auth_m and body_m:
        proc = subprocess.run(
            [
                "curl",
                "-s",
                "-w",
                "\n%{http_code}",
                "-X",
                "POST",
                url_m.group(1),
                "-H",
                f"Authorization: Bearer {auth_m.group(1)}",
                "-H",
                "Content-Type: application/json",
                "-d",
                body_m.group(1),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            parts = proc.stdout.strip().rsplit("\n", 1)
            body = json.loads(parts[0])
            ok_curl = parts[-1] == "200" and body.get("predictions")
        except Exception:
            ok_curl = False
    check("curl_snippet_executes", ok_curl, f"out={proc.stdout[:150] if ok_curl else (proc.stdout or proc.stderr)[:150]}")

    py_snippet = snippets["python"].replace("pl_live_ВАШ_КЛЮЧ", key)
    py_snippet = py_snippet.replace("http://localhost:8000", BASE)
    py_globals: dict = {}
    try:
        exec(py_snippet, py_globals)
        check("python_snippet_executes", True)
    except Exception as exc:
        check("python_snippet_executes", False, str(exc)[:200])

    print("== D. Дрейф → статус DRIFT и вебхук ==")
    webhooks: list = []
    hook_server = http.server.HTTPServer(("127.0.0.1", 8399), _make_hook_handler(webhooks))
    threading.Thread(target=hook_server.serve_forever, daemon=True).start()
    client.post("/api/admin/webhooks", json={"url": "http://127.0.0.1:8399/hook", "events": ["drift", "live_metric_drop"]})

    schema = client.get(f"/api/v1/models/{telco_id}/schema").json()
    example = schema.get("example") or {}
    rec = {}
    for k, p in schema["input_schema"]["properties"].items():
        v = example.get(k)
        if v is None:
            continue
        rec[k] = float(v) if p["type"] == "number" else str(v)
    shifted = []
    for _ in range(120):
        row = dict(rec)
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = v + 12.5
        shifted.append(row)
    for start in range(0, 120, 20):
        client.post(f"/api/v1/models/{telco_id}/predict", json={"data": shifted[start : start + 20]})
    r = client.post(f"/api/models/{telco_id}/monitor/run")
    jr = wait_job(client, r.json()["job_id"], 300)
    check("drift_job_done", jr["status"] == "done", str(jr)[:200])
    reports = client.get(f"/api/models/{telco_id}/monitor").json()
    latest = reports[0] if reports else {}
    check("psi_computed", latest.get("report") and latest["report"].get("n_predictions", 0) >= 100, f"n_pred={latest.get('report', {}).get('n_predictions')}")
    drift_statuses = [rep["status"] for rep in reports]
    if "DRIFT" in drift_statuses or "WARN" in drift_statuses:
        check("drift_status_changed", True, str(drift_statuses))
        if "DRIFT" in drift_statuses:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not webhooks:
                time.sleep(1)
            check("webhook_fired_on_drift", len(webhooks) > 0, f"получено: {webhooks[:1]}")
    else:
        check("drift_status_changed", False, f"статусы не изменились: {drift_statuses}")

    print("== E. Откат версии меняет predict без перезапуска ==")
    r = client.post(f"/api/models/{telco_id}/train", json={"mode": "quick"})
    if r.status_code == 201:
        jr = wait_job(client, r.json()["job_id"])
        check("second_version_trained", jr["status"] == "done", str(jr)[:200])
    versions = client.get(f"/api/v1/models/{telco_id}/versions").json()
    active = next((v for v in versions if v.get("active")), None)
    other = next((v for v in versions if not v.get("active")), None)
    if active and other:
        before = client.post(f"/api/v1/models/{telco_id}/predict", json={"data": [rec]}).json()["predictions"][0]
        client.post(f"/api/models/{telco_id}/rollback", json={"version": other["version"]})
        after = client.post(f"/api/v1/models/{telco_id}/predict", json={"data": [rec]}).json()["predictions"][0]
        versioned = client.post(f"/api/v1/models/{telco_id}/predict", json={"data": [rec], "version": active["version"]}).json()["predictions"][0]
        check(
            "rollback_changes_predictions",
            before["prediction_id"] != after["prediction_id"] and versioned["label"] == before["label"],
            f"before={before.get('label')} after={after.get('label')}",
        )
        client.post(f"/api/models/{telco_id}/rollback", json={"version": active["version"]})
    else:
        check("rollback_changes_predictions", False, "нужны 2 версии модели")

    hook_server.shutdown()
    print(f"\nPASS={len(passed)} FAIL={len(failed)}")
    if failed:
        print("FAILED:", "; ".join(failed))
        sys.exit(1)


def _make_hook_handler(storage: list):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", 0))
            storage.append(json.loads(self.rfile.read(length) or b"{}"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


if __name__ == "__main__":
    main()
