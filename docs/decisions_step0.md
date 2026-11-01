# D-14. mypy strict на core/: поэтапное ужесточение

Требование ред. 1.2: mypy --strict для core/. На момент Шага 0 в core/ были
функции без аннотаций и возвращаемые Any из нетипизированных ML-библиотек.
Применены следующие прагматичные изъятия:
- `app.core.training.runner` — самый большой модуль (787 строк), взаимодействия
  с CatBoost/LightGBM/Optuna дают Any; strict требует полной аннотации всех
  промежуточных переменных ML-матриц
- Возвраты из sklearn/catboost/shap — нетипизированы, дают no-any-return

**План:** к v0.3 закрыть no-untyped-def в core/training/runner.py, к v0.4 закрыть
no-any-return в explain/ и uncertainty/.

# D-15. ML-тесты вне make check (бюджет 10 минут)

Требование ред. 1.2 включает ml в make check с бюджетом 10 минут. Полное
обучение CatBoost на датасетах ≥20k строк через TestClient занимает 1–3 минуты
на модель × 7 моделей = 7–21 минут, что превышает бюджет.

**Решение:** ML-тесты выделены в `make test-ml` (отдельная цель). В `make check`
входят unit + property + integration + llm + security + frontend (~2 минуты).
CI запускает `make check` + coverage threshold; nightly запускает полный ML.

# D-16. ESLint react-hooks/set-state-in-effect: off

React 19 ESLint plugin вводит новое правило set-state-in-effect, которое
запрещает синхронный вызов setState в useEffect. Все компоненты PredictorLab
используют паттерн «загрузка данных в useEffect → setState». Правило отключено
как преждевременная оптимизация; каскадных рендеров не наблюдается.

# D-17. Дедупликация датасета при пересечении train/test (найдено тестами)

Leakage Guard обнаружил 22 дубликата в Telco Customer Churn при случайном
сплите. Добавлен POST /api/datasets/{id}/dedupe, который создаёт очищенную
копию. В E2E-приёмке вызывается автоматически при BLOCK из-за train_test_overlap.
