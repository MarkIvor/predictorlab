"""Smoke-тест MCP-сервера PredictorLab через stdio-транспорт."""

import asyncio
import os
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "mcp/src")

from mcp.client.stdio import stdio_client

from mcp import ClientSession, StdioServerParameters

BASE = "http://localhost:8200"


async def main():
    login = httpx.post(f"{BASE}/api/auth/login", json={"email": "admin@predictorlab.io", "password": "predictorlab2026"})
    assert login.status_code == 200
    client = httpx.Client(base_url=BASE, cookies=login.cookies, timeout=60)
    key = client.post("/api/keys", json={"name": "mcp-smoke", "model_ids": []}).json()["key"]

    env = {
        **os.environ,
        "PREDICTORLAB_URL": BASE,
        "PREDICTORLAB_API_KEY": key,
        "PYTHONPATH": "mcp/src",
        "PYTHONIOENCODING": "utf-8",
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "predictorlab_mcp"], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", names)
            assert "list_models" in names and "predict" in names and "get_drift_status" in names

            result = await session.call_tool("list_models", {})
            models_text = result.content[0].text
            assert '"id"' in models_text
            print("LIST_MODELS ok:", models_text[:120].replace("\n", " "))

            import json as _json

            models = _json.loads(models_text)
            ready = next((m for m in models if m.get("status") == "ready" and m.get("task_type") == "binary"), None)
            assert ready, "нет готовой бинарной модели"
            mid = ready["id"]

            schema = _json.loads((await session.call_tool("get_model_schema", {"model_id": mid})).content[0].text)
            example = schema.get("example") or {}
            rec = {k: v for k, v in example.items() if v is not None}

            pred = (await session.call_tool("predict", {"model_id": mid, "data": [rec], "include": ["reasons"]})).content[0].text
            assert '"probability"' in pred and "top_reasons" in pred
            print("PREDICT ok:", pred[:140].replace("\n", " "))

            explain = (await session.call_tool("explain", {"model_id": mid, "data": rec})).content[0].text
            assert "top_reasons" in explain
            print("EXPLAIN ok")

            card = (await session.call_tool("get_model_card", {"model_id": mid})).content[0].text
            assert "Model Card" in card
            print("CARD ok:", len(card), "chars")

            drift = (await session.call_tool("get_drift_status", {"model_id": mid})).content[0].text
            print("DRIFT ok:", drift[:100].replace("\n", " "))

    print("MCP SMOKE PASS")


asyncio.run(main())
