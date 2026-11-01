"""E2E мониторинга и живых функций: feedback → дрейф → вебхук-заглушка → плейбук → Prometheus → публичная страница."""
import io
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8200"

passed: list[str] = []
failed: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    (passed if cond else failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else f" {detail}"))


def main():
    client = httpx.Client(base_url=BASE, timeout=600)
    r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab2026"})
    assert r.status_code == 200, r.text
    models = client.get("/api/models").json()
    model = next((m for m in models if m["status"] == "ready" and m["task_type"] == "binary"), None)
    assert model, "нет готовой бинарной модели"
    mid = model["id"]

    print("== 1. Прогнозы пишутся в лог ==")
    schema = client.get(f"/api/v1/models/{mid}/schema").json()
    example = schema.get("example") or {}
    r = client.post(f"/api/v1/models/{mid}/predict", json={"data": [example], "include": ["reasons"]})
    check("predict_before_log", r.status_code == 200, r.text[:200])
    preds = client.get(f"/api/models/{mid}/predictions?limit=20").json()
    check("prediction_log_filled", len(preds) > 0, f"{len(preds)} записей")
    masked_ok = all("@" not in str(p.get("input", {})).replace("@***", "") or "***" in str(p.get("input", {})) for p in preds[:5])
    check("pii_masked_or_absent", masked_ok)

    print("== 2. Feedback и live-метрики ==")
    for p in preds[:10]:
        actual = 1 if (p["output"] or {}).get("probability", 0) > 0.5 else 0
        r = client.post(f"/api/models/{mid}/feedback", json={"prediction_id": p["prediction_id"], "actual": actual})
    check("feedback_accepted", r.status_code == 201, r.text[:200])

    print("== 3. Дрейф-джоба ==")
    r = client.post(f"/api/models/{mid}/monitor/run")
    check("drift_started", r.status_code == 202, r.text[:200])
    job_id = r.json()["job_id"]
    for _ in range(120):
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(2)
    check("drift_done", jr["status"] == "done", str(jr)[:300])
    reports = client.get(f"/api/models/{mid}/monitor").json()
    check("drift_report", len(reports) > 0 and "status" in reports[0], str(reports[:1])[:200])
    print(f"  отчёт: status={reports[0]['status']}, n_predictions={reports[0]['report'].get('n_predictions')}")

    print("== 4. Prometheus ==")
    metrics = client.get("/api/metrics").text
    check("prometheus_predict_total", "predictorlab_predict_requests_total" in metrics)
    check("prometheus_latency", "predictorlab_predict_latency_seconds" in metrics)

    print("== 5. Разметка actionable + плейбук ==")
    num_col = next((k for k, v in schema["input_schema"]["properties"].items() if v["type"] == "number"), None)
    assert num_col, "нет числовой колонки в схеме"
    r = client.patch(f"/api/models/{mid}", json={"actionable": {
        num_col: {"min": 0, "max": 100, "direction": "both", "cost_per_unit": 100}}})
    check("actionable_saved", r.status_code == 200, r.text[:200])
    r = client.post(f"/api/v1/models/{mid}/counterfactual", json={"data": example})
    check("counterfactual_responds", r.status_code == 200 and ("found" in r.json() or "detail" in r.json()), r.text[:200])

    buf = io.StringIO()
    cols = list(example.keys())[:8]
    buf.write(",".join(cols) + "\n")
    for i in range(30):
        row = {c: example.get(c) for c in cols}
        if num_col in row and row[num_col] is not None:
            row[num_col] = 50 + i
        buf.write(",".join("" if row[c] is None else str(row[c]) for c in cols) + "\n")
    r = client.post(f"/api/models/{mid}/playbook", files={"file": ("base.csv", buf.getvalue().encode(), "text/csv")})
    check("playbook_started", r.status_code == 202, r.text[:300])
    play_job = r.json()["job_id"]
    for _ in range(240):
        jr = client.get(f"/api/jobs/{play_job}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(2)
    check("playbook_done", jr["status"] == "done", str(jr)[:300])
    if jr["status"] == "done":
        csv_res = client.get(f"/api/v1/jobs/{play_job}/result/playbook.csv")
        check("playbook_csv", csv_res.status_code == 200 and b"recommendation" in csv_res.content, str(csv_res.status_code))

    print("== 6. Публичная страница прогноза ==")
    r = client.post(f"/api/public/manage/{mid}", json={"enabled": True, "password": "demo1234"})
    check("public_enabled", r.status_code == 201 and r.json().get("url"), r.text[:200])
    slug = r.json()["url"].rsplit("/", 1)[-1]
    pub = httpx.Client(base_url=BASE, timeout=60)
    info = pub.get(f"/api/public/p/{slug}").json()
    check("public_info", info.get("has_password") is True, str(info)[:200])
    r = pub.post(f"/api/public/p/{slug}/predict", json={"data": example, "password": "demo1234"})
    check("public_predict", r.status_code == 200 and "prediction" in r.json(), r.text[:200])
    r = pub.post(f"/api/public/p/{slug}/predict", json={"data": example, "password": "wrong"})
    check("public_wrong_password", r.status_code == 401, r.text[:100])
    client.post(f"/api/public/manage/{mid}", json={"enabled": False})

    print("== 7. Контрфактуал: immutable не меняются (property-проверка) ==")
    r = client.patch(f"/api/models/{mid}", json={"actionable": {
        num_col: {"immutable": True}}})
    cf = client.post(f"/api/v1/models/{mid}/counterfactual", json={"data": example}).json()
    check("cf_needs_actionable", cf.get("found") is False or "разметьте" in str(cf.get("detail", "")), str(cf)[:200])

    print(f"\nPASS={len(passed)} FAIL={len(failed)}")
    if failed:
        print("FAILED:", "; ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
