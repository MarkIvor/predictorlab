import json
import os

from mcp.server.fastmcp import FastMCP

from .client import PredictorLabClient

mcp = FastMCP("PredictorLab")


def _client() -> PredictorLabClient:
    base = os.environ.get("PREDICTORLAB_URL", "http://localhost:8000")
    key = os.environ.get("PREDICTORLAB_API_KEY", "")
    jwt = os.environ.get("PREDICTORLAB_JWT")
    if not key and not jwt:
        raise ValueError("Задайте PREDICTORLAB_API_KEY (ключ pl_live_…) или PREDICTORLAB_JWT")
    return PredictorLabClient(base, key or "pl_live_none", jwt=jwt)


@mcp.tool()
def list_models() -> str:
    """Список моделей PredictorLab, доступных ключу: id, имя, тип задачи, метрики, статус."""
    return json.dumps(_client().list_models(), ensure_ascii=False, indent=1)


@mcp.tool()
def get_model_schema(model_id: int) -> str:
    """JSON Schema входа модели: типы полей, допустимые значения категорий, пример."""
    return json.dumps(_client().get_schema(model_id), ensure_ascii=False, indent=1)


@mcp.tool()
def predict(model_id: int, data: list[dict], include: list[str] | None = None) -> str:
    """Прогноз по 1–1000 объектам. include: ['reasons'] добавит топ-причины SHAP.

    Каждый элемент data — объект с полями по схеме модели (см. get_model_schema).
    Ответ: label/probability/decision/threshold, конформальное множество, флаг OOD.
    """
    return json.dumps(_client().predict(model_id, data, include), ensure_ascii=False, indent=1)


@mcp.tool()
def explain(model_id: int, data: dict) -> str:
    """Локальные причины прогноза для одного объекта: топ-5 признаков с вкладом."""
    return json.dumps(_client().explain(model_id, data), ensure_ascii=False, indent=1)


@mcp.tool()
def what_if(model_id: int, data: dict, changes: dict) -> str:
    """Прогноз до/после изменения признаков. changes: {признак: новое_значение}."""
    return json.dumps(_client().what_if(model_id, data, changes), ensure_ascii=False, indent=1)


@mcp.tool()
def counterfactual(model_id: int, data: dict, direction: str = "below") -> str:
    """Минимальное по стоимости изменение управляемых признаков, переводящее объект через порог.

    direction: 'below' — снизить вероятность ниже порога, 'above' — поднять.
    """
    return json.dumps(_client().counterfactual(model_id, data, direction), ensure_ascii=False, indent=1)


@mcp.tool()
def get_model_card(model_id: int) -> str:
    """Model Card в Markdown: назначение, данные, Leakage Guard, метрики, калибровка, ограничения."""
    return _client().get_model_card(model_id)


@mcp.tool()
def get_drift_status(model_id: int) -> str:
    """Статус дрейфа (PSI) и live-метрик модели по последнему отчёту."""
    return json.dumps(_client().get_drift_status(model_id), ensure_ascii=False, indent=1)


@mcp.tool()
def train_model(model_id: int, mode: str = "quick") -> str:
    """Переобучить модель (quick/full). Требует JWT и включённый MCP_ALLOW_TRAIN на сервере."""
    if os.environ.get("MCP_ALLOW_TRAIN", "false").lower() != "true":
        return "Обучение через MCP отключено (MCP_ALLOW_TRAIN=false). Запустите обучение в UI."
    return json.dumps(_client().train_model(model_id, mode), ensure_ascii=False, indent=1)
