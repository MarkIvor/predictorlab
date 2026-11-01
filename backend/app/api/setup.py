import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_role
from app.config import get_settings
from app.core.registry import artifacts
from app.models.database import Model, ModelVersion, User

router = APIRouter(prefix="/api", tags=["setup"])


def _owned_version(model_id: int, user: User, db: Session) -> tuple[Model, ModelVersion]:
    m = db.get(Model, model_id)
    if m is None or (user.role != "admin" and m.user_id != user.id):
        raise HTTPException(status_code=404, detail="Модель не найдена")
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    return m, v


@router.get("/models/{model_id}/snippets")
def snippets(model_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m, v = _owned_version(model_id, user, db)
    settings = get_settings()
    vdir = settings.storage_path / v.dir_path
    schema = artifacts.load_json(vdir / "schema.json")
    example = schema.get("example") or {}
    record = {k: ("" if val is None else val) for k, val in example.items()}
    body = {"data": [record]}
    body_json = json.dumps(body, ensure_ascii=False)
    url = f"{settings.public_base_url.replace(':3000', ':8000')}/api/v1/models/{m.id}/predict"

    curl = f'curl -X POST "{url}" \\\n  -H "Authorization: Bearer pl_live_ВАШ_КЛЮЧ" \\\n  -H "Content-Type: application/json" \\\n  -d \'{body_json}\''
    python = (
        "import requests\n\n"
        f"response = requests.post(\n"
        f'    "{url}",\n'
        f'    headers={{"Authorization": "Bearer pl_live_ВАШ_КЛЮЧ"}},\n'
        f"    json={body_json and json.dumps(body, ensure_ascii=False)},\n"
        f"    timeout=30,\n"
        f")\n"
        f"print(response.json())"
    )
    javascript = (
        f'const response = await fetch("{url}", {{\n'
        f'  method: "POST",\n'
        f"  headers: {{\n"
        f'    "Authorization": "Bearer pl_live_ВАШ_КЛЮЧ",\n'
        f'    "Content-Type": "application/json",\n'
        f"  }},\n"
        f"  body: JSON.stringify({json.dumps(body, ensure_ascii=False)}),\n"
        f"}});\n"
        f"const data = await response.json();\n"
        f"console.log(data.predictions[0]);"
    )
    one_c = (
        f'Соединение = Новый HTTPСоединение("{settings.public_base_url.replace("http://", "").replace(":3000", ":8000")}", 8000);\n'
        f'Запрос = Новый HTTPЗапрос("/api/v1/models/{m.id}/predict");\n'
        f'Запрос.Заголовки.Вставить("Authorization", "Bearer pl_live_ВАШ_КЛЮЧ");\n'
        f'Запрос.Заголовки.Вставить("Content-Type", "application/json");\n'
        f"Запрос.УстановитьТелоИзСтроки('{body_json}', КодировкаТекста.UTF8);\n"
        f'Ответ = Соединение.ОтправитьДляОбработки(Запрос, "POST");\n'
        f"Если Ответ.КодСостояния = 200 Тогда\n"
        f"    Результат = Ответ.ПолучитьТелоКакСтроку();\n"
        f"КонецЕсли;"
    )
    return {
        "model_id": m.id,
        "model_version": v.version,
        "url": url,
        "curl": curl,
        "python": python,
        "javascript": javascript,
        "one_c": one_c,
        "schema": schema["input_schema"],
        "example": example,
    }


@router.get("/llm/status")
def llm_status(user: User = Depends(get_current_user)):
    get_settings()
    from app.llm.client import llm_config

    cfg = llm_config()
    return {"enabled": cfg["enabled"], "model": cfg["model"] if cfg["enabled"] else None}


@router.post("/llm/target-from-words")
def target_from_words(body: dict, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    from app.core.guard import llm_judge
    from app.models.database import Dataset

    goal = (body or {}).get("goal", "").strip()
    dataset_id = (body or {}).get("dataset_id")
    if not goal:
        raise HTTPException(status_code=422, detail="Опишите цель словами")
    d = db.get(Dataset, dataset_id) if dataset_id else None
    if d is None:
        raise HTTPException(status_code=422, detail="Укажите dataset_id")
    result = llm_judge.suggest_target(goal, list(d.columns_meta or []))
    if result is None:
        raise HTTPException(status_code=503, detail="LLM недоступна — задайте таргет вручную")
    return {"target_col": result.target_col, "task_type": result.task_type, "sql": result.sql, "explanation": result.explanation}  # type: ignore[typeddict-item]


@router.post("/llm/feature-suggestions")
def feature_suggestions(body: dict, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    from app.core.features import builder
    from app.core.guard import llm_judge
    from app.models.database import Connection

    config = (body or {}).get("config") or {}
    conn_id = config.get("connection_id")
    if not conn_id:
        raise HTTPException(status_code=422, detail="Укажите connection_id в конфиге")
    conn_row = db.get(Connection, int(conn_id))
    if conn_row is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    conn = builder.connection_connector(conn_row)
    describes = {}
    for table in [config.get("main_table")] + [c.get("table") for c in config.get("children", [])]:
        if table:
            try:
                describes[table] = conn.describe(table)
            except Exception:
                describes[table] = []
    result = llm_judge.suggest_features(config, describes)
    if result is None:
        raise HTTPException(status_code=503, detail="LLM недоступна")
    if hasattr(result, "features"):
        return {"features": list(result.features)}
    return {"features": []}


@router.post("/llm/judge/{model_id}")
def llm_judge_model(model_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    from app.core.guard import llm_judge
    from app.models.database import Dataset, Model

    m = db.get(Model, model_id)
    if m is None or (user.role != "admin" and m.user_id != user.id):
        raise HTTPException(status_code=404, detail="Модель не найдена")
    d = db.get(Dataset, m.dataset_id)
    if d is None:
        raise HTTPException(status_code=422, detail="Укажите dataset_id")
    result = llm_judge.judge_columns(list(d.columns_meta or []), m.target_col, m.task_type)
    if result is None:
        raise HTTPException(status_code=503, detail="LLM недоступна — работают детерминированные проверки")
    return result


@router.get("/setup/mcp-config")
def mcp_config(user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.mcp_auth_token:
        return {"enabled": False, "detail": "Задайте MCP_AUTH_TOKEN в .env, чтобы включить MCP-сервер"}
    base = settings.public_base_url.replace(":3000", ":8000")
    claude = {
        "mcpServers": {
            "predictorlab": {
                "command": "predictorlab-mcp",
                "args": ["--transport", "stdio", "--url", base, "--auth-token", settings.mcp_auth_token],
            }
        }
    }
    cursor = {
        "mcpServers": {
            "predictorlab": {
                "url": f"{base}/mcp",
                "headers": {"Authorization": f"Bearer {settings.mcp_auth_token}"},
            }
        }
    }
    return {
        "enabled": True,
        "claude_desktop": json.dumps(claude, indent=2, ensure_ascii=False),
        "cursor": json.dumps(cursor, indent=2, ensure_ascii=False),
        "http_command": f"predictorlab-mcp --transport http --host 0.0.0.0 --port 8100 --url {base} --auth-token <token>",
        "allow_train": settings.mcp_allow_train,
    }
