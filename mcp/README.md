# predictorlab-mcp

MCP-сервер PredictorLab: прогнозы, причины, what-if, контрфактуалы, Model Card и статус дрейфа — прямо из Claude Desktop, Cursor или любого MCP-клиента.

## Установка

```bash
pip install ./mcp
# или в окружение PredictorLab:
pip install -e ./mcp
```

## Запуск

```bash
# stdio (Claude Desktop, Cursor CLI)
predictorlab-mcp --transport stdio --url http://localhost:8000 --api-key pl_live_...

# HTTP (для Cursor и веб-клиентов), Bearer-токен самого MCP
predictorlab-mcp --transport http --host 0.0.0.0 --port 8100 --url http://localhost:8000 \
  --api-key pl_live_... --auth-token <токен-mcp>
```

Ключи и URL можно задавать переменными: `PREDICTORLAB_URL`, `PREDICTORLAB_API_KEY`, `PREDICTORLAB_JWT`, `PREDICTORLAB_MCP_AUTH_TOKEN`.

## Тулы

| Тул | Что делает |
|---|---|
| `list_models` | Список доступных ключу моделей с метриками |
| `get_model_schema` | JSON Schema входа модели + пример |
| `predict` | Прогноз 1–1000 объектов; `include=["reasons"]` — топ-причины SHAP |
| `explain` | Локальные причины для одного объекта |
| `what_if` | Прогноз до/после изменения признаков |
| `counterfactual` | Минимальное по стоимости действие через порог |
| `get_model_card` | Model Card (Markdown) с Leakage Guard и ограничениями |
| `get_drift_status` | Последний отчёт PSI-дрейфа и live-метрик |
| `train_model` | Переобучение — только при `MCP_ALLOW_TRAIN=true` и JWT |

## Конфиги клиентов

Готовые конфиги генерируются в админке PredictorLab (ADMIN → MCP) с кнопками «Скопировать» и «Скачать».
