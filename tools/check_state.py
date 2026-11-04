import httpx

client = httpx.Client(base_url="http://localhost:8200", timeout=30)
r = client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab"})
if r.status_code == 200:
    models = client.get("/api/models").json()
    for m in models:
        print(f"  {m['name']:<30} status={m['status']:<10} AUC/MAE={m.get('hero_metric', '—')}")
    jobs = client.get("/api/jobs?all=1").json() if hasattr(client, "get") else []
else:
    print("login failed:", r.status_code)
