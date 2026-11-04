# PredictorLab

> Load your data. Say what you want to predict. Get an honest model, a forecast in rubles, and an API — all in 5 minutes.

**Self-hosted tabular ML for people without a Data Science team.** Upload a file → pick a target → get a model → predict via UI, file, web form, or **REST API**. The system catches **target leakage**, splits time-series data correctly, gives **honest confidence intervals**, and finds the **profit-maximizing threshold** — not just the best F1.

[![CI](https://github.com/MarkIvor/predictorlab/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MarkIvor/predictorlab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg?logo=docker)](https://docs.docker.com/compose/)
[![make check](https://img.shields.io/badge/make%20check-passing-brightgreen.svg)](#tests--ci)

[Русская версия](README.ru.md) · English

## Why not Obviously AI / DataRobot / H2O?

| | Obviously AI | DataRobot / H2O | **PredictorLab** |
|---|---|---|---|
| Target leakage | Doesn't detect it — "99% accuracy" | Partial | **Leakage Guard: BLOCK + explanation in plain English/Russian** |
| Confidence interval | Just probability | Model-specific | **Conformal prediction: interval/set with coverage guarantee + OOD flag** |
| Decision threshold | 0.5 or F1 | Manual tuning | **Cost matrix → profit-maximizing threshold, top-K capacity** |
| Time-series split | Random | Manual | **Automatic out-of-time split + group split** |
| Feature store | Need flat file | Separate ETL | **Built-in Point-in-Time Feature Builder from your DB** |
| What to do with a prediction | — | — | **Counterfactuals: minimum-cost action + playbook** |
| Self-hosted & offline | No | Yes, but heavy | **Docker, works fully without LLM or internet** |
| Price | SaaS | $$$$ | **MIT** |

## How it looks

| | |
|---|---|
| ![Login](docs/screenshots/01_login.png) | ![Hangar](docs/screenshots/02_hangar.png) |
| *Login page* | *Model hangar — AUC, profit, guard verdict per tile* |
| ![Overview](docs/screenshots/03_overview.png) | ![What-If](docs/screenshots/04_whatif.png) |
| *Overview: "What does this mean?" + calibration + drivers* | *What-If: live sliders, interval recalculates* |
| ![Profit](docs/screenshots/05_profit.png) | ![Predict](docs/screenshots/06_predict.png) |
| *Profit: cost matrix → threshold by money, not F1* | *Single prediction: probability + interval + reasons* |
| ![Share](docs/screenshots/07_api_share.png) | ![Card](docs/screenshots/08_model_card.png) |
| *Share predictions: web form, API key, batch — 3 paths* | *Model Card: auto-generated, exportable* |
| ![Wizard](docs/screenshots/09_wizard_data.png) | ![Admin](docs/screenshots/10_admin.png) |
| *5-step wizard: Data → Target → Health → Train → Result* | *Admin: users, LLM, connections, webhooks* |

## How it works

```
 UI :3000 ████  REST API :8000 ████  MCP :8100
    │                     │                     │
    └─────────────────────┼─────────────────────┘
                          ▼
          ┌────────────────────────────────────┐
          │  FastAPI + asyncio jobs + SSE      │
          ├────────────────────────────────────┤
          │  Ingest: CSV/XLSX/Parquet, PII     │
          │  Feature Builder: point-in-time    │
          │  Leakage Guard → splits → training  │
          │  CatBoost/LightGBM + Optuna        │
          │  Conformal + OOD + SHAP + Profit    │
          │  Monitoring: PSI drift + webhooks   │
          ├────────────────────────────────────┤
          │  DuckDB (data) · SQLite (metadata)  │
          │  storage/models/{id}/v{n}/ artifacts│
          └────────────────────────────────────┘
```

## Leakage Guard: how it saves your project

Upload a dataset with a trap — a `cancel_date` column filled only for churned customers:

```
[x] «cancel_date» almost perfectly predicts the target (AUC 0.998) — looks like leakage
[x] «final_status» name resembles a post-event feature — flagged by suspicious-name check
[x] «cancel_date» contains dates after the event time (100% of rows) — feature from the future

Verdict: BLOCK — results will not be shown
[EXCLUDE (cancel_date, final_status) AND RETRAIN]
```

After "Exclude and retrain", ROC-AUC drops from ~0.99 to ~0.85 — that's the **real** model, not a leakage artifact. Advanced users can override the block (checkbox) — the decision is recorded in the Model Card.

## Quick Start

```bash
git clone https://github.com/MarkIvor/predictorlab.git
cd predictorlab
cp .env.example .env    # change ADMIN_EMAIL / ADMIN_PASSWORD / secrets
docker compose up -d
# UI: http://localhost:3000  ·  API: http://localhost:8000  ·  /docs
```

**Dev without Docker:**
```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

Then: log in with the default admin (password change required on first login), upload `demo-data/telco.csv` or `demo-data/b2b_leaky.csv` (with the leak — check Leakage Guard), pick a target, click **Quick Train**.

**Works fully offline and without LLM.** When `LLM_BASE_URL` is empty, LLM features are hidden — training and predictions don't depend on external services. LLM (any OpenAI-compatible API) is used only for texts, feature suggestions, and semantic column checks — raw data rows never leave the system.

## Predict in 60 seconds

```bash
# 1. Create a key in the UI (API tab): shown once, stored as hash
export KEY=pl_live_...

# 2. Get the schema
curl http://localhost:8000/api/v1/models/1/schema -H "Authorization: Bearer $KEY"

# 3. Predict with reasons
curl -X POST http://localhost:8000/api/v1/models/1/predict \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"data": [{"days_since_last_order": 75, "satisfaction": 2.1}], "include": ["reasons"]}'
```

Response: probability, decision by your profit threshold, conformal set, OOD flag, and top reasons in plain language. Snippets for curl / Python / JS / **1C** are auto-generated per model schema and work without edits.

## Share predictions

Three ways, one click each:

1. **Web form** — create a link; anyone can predict without login. Optional password protection.
2. **API key** — for developers; snippets in curl, Python, JavaScript, and 1C + sandbox.
3. **Batch** — upload a CSV → background job → download predictions with intervals.

## MCP Server

```bash
predictorlab-mcp --transport stdio --url http://localhost:8000 --api-key pl_live_...
```

Tools: `list_models`, `get_model_schema`, `predict`, `explain`, `what_if`, `counterfactual`, `get_model_card`, `get_drift_status`. Training via MCP is behind a flag.

## Benchmarks

| Operation | Budget | Measured |
|---|---|---|
| `predict`, 1 record | < 300 ms | **62 ms** |
| `predict` + SHAP reasons | < 1 s | **79 ms** |
| Batch 10k rows | < 2 min | **14 s** |
| Train quick, 50k × 50 | ~2 min | **155 s** |
| Counterfactual, 1 object | < 10 s | **6.4 s** |

Full results: [BENCHMARKS.md](BENCHMARKS.md) · Run: `make bench`

## Honesty & Limitations

- **Counterfactuals ≠ causality.** "Reduce discount by 5% → probability drops to 0.31" is the model's response to a feature change, not a proven causal effect.
- **Conformal guarantee is marginal.** 90% coverage holds on average, not for every single object. For imbalanced classes, set coverage may exceed α — that's a property of the method (see DECISIONS.md D-12).
- **Small datasets give wide intervals.** 200 rows → interval is almost useless. We show this honestly, not hide it.
- **Profit in rubles is based on your assumptions.** All formulas and coefficients are expandable; the "+1.84M ₽" figure is only as good as your cost/benefit estimates.
- **LLM never affects the numbers.** Training, probabilities, intervals, thresholds, and profit are deterministic code. LLM only writes texts — and those pass a number validator.
- **Time-series forecasting (v0.3)** is pragmatic: lags + rolling stats + calendar, one series at a time. Strong exotic seasonality is not modeled (DECISIONS.md D-10).

## Tests & CI

```bash
make check    # lint + typecheck + unit + property + integration + llm + security + frontend (~2 min)
make test-e2e # Playwright end-to-end
make test-ml  # ML quality tests (golden datasets, determinism, invariants)
make bench    # performance benchmarks
```

- **ruff** (lint + format), **mypy** (strict for `core/`), **pytest** + **hypothesis** (property-based)
- **vitest** + **eslint** + **tsc** for frontend
- **CI**: GitHub Actions — lint → typecheck → `make check` → coverage threshold → e2e smoke
- **Nightly**: full e2e, benchmarks, ML tests

## Tech Stack

| Layer | |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SSE, asyncio jobs |
| ML | scikit-learn, CatBoost, LightGBM, Optuna, SHAP, own split-conformal |
| Data | DuckDB (data), SQLite (metadata), PostgreSQL/MySQL/ClickHouse/SQLite connectors (read-only) |
| Frontend | React 19, TypeScript, Vite, Recharts, CSS custom properties |
| MCP | FastMCP (stdio + HTTP, Bearer auth) |
| Infra | Docker, docker-compose, GitHub Actions, pre-commit |

## License

MIT — like all Ivor's Lab repositories. Telco Customer Churn © IBM (Apache 2.0), California Housing from A. Géron's course; both datasets included in `demo-data/` for offline demos.
