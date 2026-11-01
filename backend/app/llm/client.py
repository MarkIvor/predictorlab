import json

import httpx

from app.config import get_settings
from app.models.database import AppSetting, SessionLocal


def llm_config() -> dict:
    settings = get_settings()
    cfg = {
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "allow_samples": settings.llm_allow_samples,
        "enabled": False,
    }
    db = SessionLocal()
    try:
        row = db.get(AppSetting, "llm")
        if row and row.value:
            v = row.value
            if v.get("base_url"):
                cfg["base_url"] = v["base_url"]
            if v.get("model"):
                cfg["model"] = v["model"]
            if v.get("api_key"):
                cfg["api_key"] = v["api_key"]
    finally:
        db.close()
    cfg["enabled"] = bool(cfg["base_url"])
    return cfg


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def chat_json(system: str, user: str, retries: int = 2, timeout: float = 60.0) -> dict | None:
    cfg = llm_config()
    if not cfg["enabled"]:
        return None
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    url = cfg["base_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + ("/v1/chat/completions" if not url.endswith("/v1") else "/chat/completions")
    for _ in range(retries + 1):
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(_strip_fences(content))
        except Exception:
            continue
    return None


def enabled() -> bool:
    return llm_config()["enabled"]
