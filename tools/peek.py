import sys
import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = httpx.Client(base_url="http://localhost:8200", timeout=10)
c.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab"})
for m in c.get("/api/models").json():
    print(f"  {m['name']:<32} status={m['status']:<10} metric={m.get('hero_metric', '-')}")
