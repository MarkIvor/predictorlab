"""Загружает демо-датасеты, обучает модели и наполняет ангар."""

import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://localhost:8200"
DEMO = "demo-data"
PASS = "predictorlab"

client = httpx.Client(base_url=BASE, timeout=1200)

r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": PASS})
assert r.status_code == 200, f"Login failed: {r.text}"
print("✓ Логин ок")


def upload_and_train(csv_name: str, model_name: str, target: str, task: str = "binary") -> dict:
    with open(f"{DEMO}/{csv_name}", "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (csv_name, f, "text/csv")}, data={"name": model_name})
    assert r.status_code == 201, f"Upload {csv_name}: {r.text[:200]}"
    ds_id = r.json()["id"]
    print(f"  ✓ Загружен {csv_name} ({r.json()['nrows']} строк)")

    event_col = next((c["name"] for c in r.json()["columns"] if c["type"] == "datetime"), None)
    body = {"dataset_id": ds_id, "name": model_name, "target_col": target, "task_type": task}
    if event_col:
        body["event_time_col"] = event_col
    r = client.post("/api/models", json=body)
    assert r.status_code == 201, f"Model {model_name}: {r.text[:300]}"
    model = r.json()
    print(f"  ✓ Модель {model_name} создана, guard={model.get('guard_verdict')}")

    excluded = list(set((model.get("excluded_cols") or []) + [c["name"] for c in client.get(f"/api/datasets/{ds_id}").json()["columns"] if c["type"] == "id"]))
    for c in (model.get("guard_report") or {}).get("exclude_auto", {}):
        excluded.append(c)

    if (model.get("guard_report") or {}).get("verdict") == "BLOCK":
        checks = (model.get("guard_report") or {}).get("checks", [])
        block_cols = [c.get("column") for c in checks if c["verdict"] == "BLOCK" and c.get("column")]
        excluded.extend(block_cols)
        if any(c["id"] == "train_test_overlap" for c in checks if c["verdict"] == "BLOCK"):
            dedup = client.post(f"/api/datasets/{ds_id}/dedupe")
            if dedup.status_code == 201:
                print(f"  ⚠ Дубликаты найдены — дедупликация: {dedup.json()['nrows']} строк")
                r2 = client.post(
                    "/api/models",
                    json={"dataset_id": dedup.json()["id"], "name": model_name, "target_col": target, **({"event_time_col": event_col} if event_col else {})},
                )
                if r2.status_code == 201:
                    model = r2.json()
                    print(f"  ✓ Модель {model_name} на очищенном датасете, guard={model.get('guard_verdict')}")
                    excluded = list(
                        set(
                            (model.get("excluded_cols") or [])
                            + block_cols
                            + [c["name"] for c in client.get(f"/api/datasets/{dedup.json()['id']}").json()["columns"] if c["type"] == "id"]
                        )
                    )

    client.patch(f"/api/models/{model['id']}", json={"excluded_cols": list(set(excluded))})
    client.post(f"/api/models/{model['id']}/recheck")

    r = client.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
    assert r.status_code == 201, f"Train {model_name}: {r.text[:200]}"
    job_id = r.json()["job_id"]

    for _ in range(600):
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(3)

    if jr["status"] != "done":
        print(f"  ⚠ Train {model_name}: {jr['status']} — {str(jr.get('error', ''))[:100]}")
        return model

    detail = client.get(f"/api/models/{model['id']}").json()
    metrics = detail.get("metrics") or {}
    auc = metrics.get("roc_auc") or metrics.get("mae")
    print(f"  ✓ {model_name} обучен: AUC/MAE={auc}")
    return detail


def set_profit(model_id: int, benefit: int = 40000, action: int = 1500, fn: int = 8000, cap: int | None = None):
    body = {"benefit_tp": benefit, "action_cost": action, "fn_cost": fn, "period_label": "holdout = 1 месяц", "scale": 1}
    if cap:
        body["capacity"] = cap
    r = client.post(f"/api/models/{model_id}/profit", json=body)
    if r.status_code == 200:
        info = r.json()
        print(f"  ✓ Профит: порог={info.get('threshold', '—')}, прибыль={info.get('profit', '—')} ₽")
    else:
        print(f"  ⚠ Профит: {r.text[:100]}")


def make_public(model_id: int, slug: str):
    r = client.post(f"/api/public/manage/{model_id}", json={"enabled": True, "slug": slug})
    if r.status_code == 201:
        print(f"  ✓ Публичная страница: /p/{slug}")
    return r.json()


print("\n=== Загружаю демо-данные ===\n")

# 1. Telco Customer Churn — классификация
print("1. Telco Customer Churn (классификация)")
telco = upload_and_train("telco.csv", "Telco Churn", "Churn")
set_profit(telco["id"], benefit=50000, action=2000, fn=10000, cap=500)
make_public(telco["id"], "telco-churn")

# 2. Цены на жильё — регрессия
print("\n2. California Housing (регрессия)")
housing = upload_and_train("housing.csv", "Housing Prices", "median_house_value", task="regression")

# 3. B2B Churn с утечкой — демонстрация Leakage Guard
print("\n3. B2B Churn (с утечкой)")
leaky = upload_and_train("b2b_leaky.csv", "B2B Churn (Leak Demo)", "churn")
set_profit(leaky["id"], benefit=40000, action=1500, fn=8000)

# 4. B2B Flat — чистый датасет для what-if
print("\n4. B2B Flat (чистый)")
flat = upload_and_train("b2b_flat.csv", "B2B Churn (Clean)", "churn")
set_profit(flat["id"], benefit=30000, action=1000, fn=5000, cap=200)

# 5. Создаём API-ключ для демо
print("\n5. API-ключ для песочницы")
r = client.post("/api/keys", json={"name": "Demo Key", "model_ids": []})
if r.status_code == 201:
    key = r.json()["key"]
    print(f"  ✓ Ключ: {key[:20]}...")

print("\n=== Готово ===\n")
models = client.get("/api/models").json()
for m in models:
    status = "🟢" if m["status"] == "ready" else "🟡" if m["status"] == "training" else "⚪"
    hero = m.get("hero_metric", "—")
    print(f"  {status} {m['name']:<30} status={m['status']:<10} AUC/MAE={hero} guard={m['guard_verdict']}")
