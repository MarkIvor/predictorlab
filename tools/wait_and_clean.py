import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = httpx.Client(base_url="http://localhost:8200", timeout=30)
client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab"})

# Ждём Housing
for _ in range(60):
    models = client.get("/api/models").json()
    housing = next((m for m in models if m["name"] == "Housing Prices" and m["status"] == "ready"), None)
    if housing:
        print(f"OK Housing: MAE={housing.get('hero_metric', '-')}")
        break
    time.sleep(3)
else:
    print("Housing still training...")

# Удаляем черновики
models = client.get("/api/models").json()
for m in models:
    if m["status"] == "draft":
        client.delete(f"/api/models/{m['id']}")
        print(f"  Deleted draft: {m['name']}")

print("\nCurrent state:")
for m in client.get("/api/models").json():
    print(f"  {m['name']:<30} status={m['status']:<10} metric={m.get('hero_metric', '-')}")
