import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8200"
client = httpx.Client(base_url=BASE, timeout=1200)
r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab"})
assert r.status_code == 200


def upload_train(csv, name, target, task="binary"):
    with open(f"demo-data/{csv}", "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (csv, f, "text/csv")}, data={"name": name})
    if r.status_code != 201:
        print(f"SKIP upload {csv}: {r.text[:100]}")
        return None
    ds = r.json()
    print(f"  uploaded {csv} ({ds['nrows']} rows)")

    event_col = next((c["name"] for c in ds["columns"] if c["type"] == "datetime"), None)
    body = {"dataset_id": ds["id"], "name": name, "target_col": target, "task_type": task}
    if event_col:
        body["event_time_col"] = event_col
    r = client.post("/api/models", json=body)
    model = r.json()
    guard = (model.get("guard_report") or {}).get("verdict", "OK")
    print(f"  model created, guard={guard}")

    excluded = list(set((model.get("excluded_cols") or []) + [c["name"] for c in ds["columns"] if c["type"] == "id"]))
    for c in (model.get("guard_report") or {}).get("exclude_auto", {}):
        excluded.append(c)
    for c in (model.get("guard_report") or {}).get("checks", []):
        if c["verdict"] == "BLOCK" and c.get("column"):
            excluded.append(c["column"])

    if guard == "BLOCK" and any(c["id"] == "train_test_overlap" for c in model["guard_report"]["checks"] if c["verdict"] == "BLOCK"):
        dedup = client.post(f"/api/datasets/{ds['id']}/dedupe")
        if dedup.status_code == 201:
            print(f"  dedup: {dedup.json()['nrows']} rows")
            r2 = client.post("/api/models", json={"dataset_id": dedup.json()["id"], "name": name, "target_col": target, "task_type": task})
            if r2.status_code == 201:
                model = r2.json()

    client.patch(f"/api/models/{model['id']}", json={"excluded_cols": list(set(excluded))})
    client.post(f"/api/models/{model['id']}/recheck")

    r = client.post(f"/api/models/{model['id']}/train", json={"mode": "quick"})
    if r.status_code != 201:
        print(f"  SKIP train: {r.text[:100]}")
        return model
    job_id = r.json()["job_id"]
    for _ in range(600):
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    detail = client.get(f"/api/models/{model['id']}").json()
    print(f"  trained: {detail['status']} AUC={detail.get('hero_metric', '-')}")
    return detail


def set_profit(mid, benefit, action, fn, cap=None):
    body = {"benefit_tp": benefit, "action_cost": action, "fn_cost": fn, "period_label": "holdout = 1 month", "scale": 1}
    if cap:
        body["capacity"] = cap
    r = client.post(f"/api/models/{mid}/profit", json=body)
    if r.status_code == 200:
        info = r.json()
        print(f"  profit: threshold={info.get('threshold', '-')}, profit={info.get('profit', '-')}")


print("3. B2B Churn (leak demo)")
leaky = upload_train("b2b_leaky.csv", "B2B Churn (Leak Demo)", "churn")
if leaky and leaky.get("id"):
    set_profit(leaky["id"], 40000, 1500, 8000)

print("4. B2B Flat (clean)")
flat = upload_train("b2b_flat.csv", "B2B Churn (Clean)", "churn")
if flat and flat.get("id"):
    set_profit(flat["id"], 30000, 1000, 5000, cap=200)

# Profit для Telco
print("Setting Telco profit...")
telco = next((m for m in client.get("/api/models").json() if m["name"] == "Telco Churn" and m["status"] == "ready"), None)
if telco:
    set_profit(telco["id"], 50000, 2000, 10000, cap=500)
    pub = client.post(f"/api/public/manage/{telco['id']}", json={"enabled": True, "slug": "telco-churn"})
    if pub.status_code == 201:
        print("  public page: /p/telco-churn")

# API-ключ
print("API key...")
r = client.post("/api/keys", json={"name": "Demo", "model_ids": []})
if r.status_code == 201:
    print(f"  key: {r.json()['key']}")

print("\n=== FINAL ===")
for m in client.get("/api/models").json():
    print(f"  {m['name']:<30} status={m['status']:<10} metric={m.get('hero_metric', '-')}")
