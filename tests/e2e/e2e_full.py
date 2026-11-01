"""E2E-прогон полного сценария ТЗ §4 на синтетике с утечкой. Использование: python tests/e2e_full.py [--base http://localhost:8200]."""

import argparse
import io
import sys
import time
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parents[1]
DEMO = BASE_DIR / "demo-data"

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        passed.append(name)
        print(f"  PASS {name}")
    else:
        failed.append(name)
        print(f"  FAIL {name} {detail}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8200")
    parser.add_argument("--with-server", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    server = None
    if args.with_server:
        import subprocess

        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(base.rsplit(":", 1)[1])],
            cwd=str(BASE_DIR / "backend"),
            stdout=open(BASE_DIR / "uvicorn-e2e.log", "w"),
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                httpx.get(f"{base}/api/health", timeout=3)
                break
            except Exception:
                time.sleep(1)
    try:
        _run_e2e(base)
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except Exception:
                server.kill()


def _run_e2e(base: str):
    client = httpx.Client(base_url=base, timeout=600)

    print("== 1. Логин ==")
    r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})
    check("login", r.status_code == 200, r.text[:200])
    assert r.status_code == 200

    print("== 2. Загрузка датасета с утечкой ==")
    with open(DEMO / "b2b_leaky.csv", "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": ("b2b_leaky.csv", f, "text/csv")}, data={"name": "e2e_leaky"})
    check("upload", r.status_code == 201, r.text[:300])
    dataset = r.json()
    ds_id = dataset["id"]
    cols = {c["name"]: c for c in dataset["columns"]}
    check("pii_detected", cols.get("support_email", {}).get("pii") == "email", "email должен быть помечен как ПДн")
    check("pii_excluded", cols.get("support_email", {}).get("excluded") is True, "ПДн исключены по умолчанию")

    print("== 3. Создание модели: Leakage Guard должен дать BLOCK ==")
    r = client.post("/api/models", json={"dataset_id": ds_id, "name": "e2e_churn", "target_col": "churn", "event_time_col": "event_date"})
    check("model_created", r.status_code == 201, r.text[:300])
    model = r.json()
    model_id = model["id"]
    report = model.get("guard_report") or {}
    check("guard_BLOCK", report.get("verdict") == "BLOCK", f"verdict={report.get('verdict')}")
    details = " || ".join(c["detail"] for c in report.get("checks", []))
    check("guard_names_cancel_date", "cancel_date" in details, details[:400])
    check("guard_names_final_status", "final_status" in details, details[:400])
    print(f"  guard checks: {report.get('verdict')} -> {details[:300]}")

    print("== 4. Исключить колонки утечки и переобучить ==")
    r = client.patch(f"/api/models/{model_id}", json={"excluded_cols": ["cancel_date", "final_status", "customer_id"]})
    check("patch_excluded", r.status_code == 200, r.text[:200])
    r = client.post(f"/api/models/{model_id}/recheck")
    check("recheck_not_block", r.json().get("verdict") != "BLOCK", r.text[:300])

    print("== 5. Обучение quick ==")
    r = client.post(f"/api/models/{model_id}/train", json={"mode": "quick"})
    check("train_started", r.status_code == 201, r.text[:300])
    job_id = r.json()["job_id"]
    deadline = time.monotonic() + 900
    last_status = None
    while time.monotonic() < deadline:
        jr = client.get(f"/api/jobs/{job_id}").json()
        last_status = jr["status"]
        if last_status in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    check("train_done", last_status == "done", f"status={last_status} err={(client.get(f'/api/jobs/{job_id}').json().get('error') or '')[:400]}")
    job = client.get(f"/api/jobs/{job_id}").json()

    print("== 6. Метрики ==")
    r = client.get(f"/api/models/{model_id}")
    model = r.json()
    metrics = model.get("metrics") or {}
    auc = metrics.get("roc_auc")
    check("version_ready", model.get("status") == "ready" and model.get("active_version") is not None, str(model.get("status")))
    check("auc_sane", auc is not None and 0.6 < auc < 0.95, f"roc_auc={auc}")
    coverage = metrics.get("coverage")
    check(
        "conformal_coverage",
        coverage is not None and coverage >= 0.85,
        f"coverage={coverage} (односторонняя гарантия ≥ α для дисбалансированных классов, см. DECISIONS D-12)",
    )
    (model.get("metrics") or {}).get("split_kind") or (job.get("progress", {}).get("split", {}) or {}).get("kind")
    card = client.get(f"/api/models/{model_id}/card").json()
    check("card_has_out_of_time", "out-of-time" in (card.get("card_md") or ""), "Model Card должна показывать out-of-time сплит")
    check("card_exists", bool(card.get("card_md")))

    print("== 7. API-ключ и прогноз ==")
    r = client.post("/api/keys", json={"name": "e2e", "model_ids": [model_id]})
    key = r.json().get("key")
    check("key_created", bool(key), r.text[:200])
    api = httpx.Client(base_url=base, timeout=120)
    api.headers["Authorization"] = f"Bearer {key}"

    r = api.get("/api/v1/models")
    check("v1_models_list", r.status_code == 200 and any(m["id"] == model_id for m in r.json()), r.text[:200])
    schema = api.get(f"/api/v1/models/{model_id}/schema").json()
    example = schema.get("example") or {}
    rec = {k: v for k, v in example.items() if v is not None}
    rec.setdefault("days_since_last_order", 75)
    rec.setdefault("satisfaction", 2.1)
    rec.setdefault("discount_pct", 12)
    rec.setdefault("segment", "SMB")
    rec["days_since_last_order"] = 75
    rec["satisfaction"] = 2.1
    r = api.post(f"/api/v1/models/{model_id}/predict", json={"data": [rec], "include": ["reasons"]})
    check("predict_contract", r.status_code == 200, r.text[:300])
    pred = r.json()["predictions"][0]
    check(
        "predict_fields",
        all(k in pred for k in ("prediction_id", "label", "probability", "decision", "threshold", "conformal", "out_of_distribution")),
        str(pred)[:300],
    )
    check("reasons_present", bool(pred.get("top_reasons")), str(pred)[:200])
    check("no_actions_by_default", "recommended_action" not in pred, "без include=actions действия не должно быть")

    r = api.post(f"/api/v1/models/{model_id}/predict", json={"data": [{"days_since_last_order": "много"}]})
    check("predict_422_russian", r.status_code == 422 and "ожидается number" in r.text, r.text[:200])

    r = api.post(f"/api/v1/models/{model_id}/whatif", json={"data": rec, "changes": {"satisfaction": 4.8}})
    check("whatif", r.status_code == 200 and "after" in r.json(), r.text[:200])

    print("== 8. Профит и порог ==")
    r = client.post(
        f"/api/models/{model_id}/profit",
        json={
            "benefit_tp": 40000,
            "action_cost": 1500,
            "fn_cost": 8000,
            "capacity": 300,
            "scale": 1,
            "period_label": "holdout = 1 месяц",
        },
    )
    check("profit_computed", r.status_code == 200, r.text[:300])
    info = r.json()
    threshold = info.get("threshold")
    check("threshold_not_05", threshold is not None and abs(threshold - 0.5) > 0.01, f"threshold={threshold}")
    check("profit_vs_random", isinstance(info.get("vs_random"), (int, float)), str(info)[:200])

    print("== 9. Batch-прогноз ==")
    buf = io.StringIO()
    sample_cols = list(rec.keys())
    buf.write(",".join(sample_cols) + "\n")
    for i in range(50):
        row = dict(rec)
        row["days_since_last_order"] = 10 + i * 3
        buf.write(",".join(str(row[c]) for c in sample_cols) + "\n")
    buf.seek(0)
    r = api.post(f"/api/v1/models/{model_id}/predict/batch", files={"file": ("batch.csv", buf.read().encode(), "text/csv")}, data={"include": "reasons"})
    check("batch_started", r.status_code == 202, r.text[:200])
    batch_job = r.json()["job_id"]
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        jr = api.get(f"/api/v1/jobs/{batch_job}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(2)
    check("batch_done", jr["status"] == "done", str(jr)[:300])
    csv_res = api.get(f"/api/v1/jobs/{batch_job}/result/predictions.csv")
    check("batch_csv", csv_res.status_code == 200 and b"probability" in csv_res.content, str(csv_res.status_code))

    print("== 10. Сниппеты ==")
    r = client.get(f"/api/models/{model_id}/snippets")
    check("snippets", r.status_code == 200 and all(k in r.json() for k in ("curl", "python", "javascript", "one_c")), r.text[:200])

    print("== 11. Песочница: predict через ключ повторно (rate limit не мешает) ==")
    r = api.post(f"/api/v1/models/{model_id}/predict", json={"data": [rec]})
    check("predict_again", r.status_code == 200, r.text[:200])

    print()
    print(f"PASS={len(passed)} FAIL={len(failed)}")
    if failed:
        print("FAILED:", "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
