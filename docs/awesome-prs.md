# PR-патчи для awesome-листов

Токен ограничен predictorlab — не может форкать. Вот готовые патчи + инструкции.

## 1. awesome-mcp-servers (97k ⭐)

**Форк:** https://github.com/punkpeye/awesome-mcp-servers/fork

**Куда:** секция `Data Science Tools`, между `leap-laboratories/discovery-engine` и `lihtness/gnomon-mcp` (алфавитный порядок: MarkIvor → после leap, перед lihtness)

**Строка для вставки:**
```markdown
- [MarkIvor/predictorlab](https://github.com/MarkIvor/predictorlab) 🏷️ 🤖 📊 - Self-hosted tabular ML with honest predictions: leakage guard (BLOCK + explanation), conformal intervals, profit-optimized thresholds and counterfactuals. Tools: predict, explain, what_if, counterfactual, get_model_card, get_drift_status. Works fully offline without LLM.
```

**PR title:** `Add PredictorLab — self-hosted tabular ML MCP server`
**PR body:**
```
Adds PredictorLab to Data Science Tools.

PredictorLab is a self-hosted tabular ML platform with a full MCP server (stdio + HTTP).
What makes it different from other ML tools:

- **Leakage Guard**: 9 deterministic checks that BLOCK training on leaked features
  (e.g., `cancel_date` filled only for churned customers → AUC 0.998 is fake)
- **Conformal prediction**: intervals with coverage guarantee + OOD flag, not bare probabilities
- **Profit-optimized threshold**: cost matrix → threshold that maximizes money, not F1
- **Counterfactuals**: minimum-cost action to flip a prediction (respecting immutable features)
- **Monitoring**: PSI drift detection, live metrics, webhooks, one-click retrain

Tools: `list_models`, `get_model_schema`, `predict`, `explain`, `what_if`, `counterfactual`,
`get_model_card`, `get_drift_status`. Works fully offline without LLM.

Docker, React 19 UI, REST API, MIT license.
```

---

## 2. awesome-llm-apps (143k ⭐)

**Форк:** https://github.com/Shubhamsaboo/awesome-llm-apps/fork

**Куда:** секция `Standalone Apps & Tools`

**Строка для вставки:**
```markdown
- **[PredictorLab](https://github.com/MarkIvor/predictorlab)** - Self-hosted tabular ML: upload CSV → pick a target → get an honest model with conformal intervals and a profit-optimized threshold. LLM used only for target suggestions and Model Card texts (works fully offline). Includes MCP server for Claude Desktop/Cursor integration.
```

**PR title:** `Add PredictorLab — honest tabular ML with optional LLM + MCP`
**PR body:**
```
Adds PredictorLab to Standalone Apps & Tools.

PredictorLab is self-hosted tabular ML that uses LLM only where it helps
(target suggestions from natural language, semantic column checking, Model Card texts)
and keeps all numbers deterministic (training, probabilities, intervals, profit — pure code).

Key features:
- Leakage Guard: blocks training on leaked features (cancel_date → 0.998 AUC is fake)
- Conformal prediction: intervals with coverage guarantee + OOD flag
- Cost matrix → profit-maximizing decision threshold
- What-If sliders + counterfactuals (minimum-cost action to flip prediction)
- REST API + MCP server (predict, explain, what_if, counterfactual, get_model_card)
- Works fully offline without LLM
```

---

## 3. awesome-datascience (30k ⭐)

**Форк:** https://github.com/academic/awesome-datascience/fork

**Куда:** секция с ML tools (найти по заголовку)

**Строка для вставки:**
```markdown
- [PredictorLab](https://github.com/MarkIvor/predictorlab) - Self-hosted tabular ML: leakage guard, conformal intervals, profit-optimized thresholds. Docker, REST API, MCP server. MIT.
```

**PR title:** `Add PredictorLab — honest self-hosted tabular ML`
**PR body:**
```
Adds PredictorLab.

Self-hosted tabular ML for analysts who need ML without a DS team:
- Automatic leakage detection (BLOCK + explanation + one-click fix)
- Conformal prediction intervals with coverage guarantee
- Cost matrix → profit-maximizing decision threshold (not F1)
- What-If + counterfactuals (minimum-cost action to change prediction)
- PSI drift monitoring + live metrics + webhooks
- REST API, MCP server, Docker, works offline
- MIT license
```

---

## Как применить (3 минуты на каждый)

1. **Форкни** репо кнопкой Fork на GitHub
2. **Открой** README.md в форке (кнопка ✏️ Edit)
3. **Найди** секцию (Ctrl+F по заголовку секции)
4. **Вставь** строку из патча выше
5. **Commit** → "Add PredictorLab"
6. **Pull Request** → вставь title и body из патча
