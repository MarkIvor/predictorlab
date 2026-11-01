def build_card_md(model, dataset, version, metrics: dict, manifest: dict,
                  leakage_report: dict, threshold_info: dict | None) -> str:
    task = model.task_type
    lines: list[str] = []
    lines.append(f"# Model Card: {model.name}")
    lines.append("")
    lines.append(f"**Версия:** {version.version} · **Обучена:** {version.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    lines.append("## Назначение")
    target_desc = {
        "binary": f"предсказывает вероятность события «{model.target_col}»",
        "multiclass": f"предсказывает класс колонки «{model.target_col}»",
        "regression": f"предсказывает числовое значение «{model.target_col}»",
        "timeseries": f"прогнозирует будущие значения ряда «{model.target_col}»",
    }
    lines.append(f"Модель {target_desc.get(task, model.target_col)} по объектам из датасета «{dataset.name}».")
    lines.append("")

    lines.append("## Данные")
    lines.append(f"- Период событий: по колонке «{dataset.event_time_col}»" if dataset.event_time_col else "- Колонка времени не задана — использован случайный сплит")
    lines.append(f"- Объём: {dataset.nrows:,} строк × {dataset.ncols} колонок".replace(",", " "))
    lines.append(f"- Хэш данных: `{dataset.data_hash[:16]}…`")
    lines.append("")

    excluded = [
        c for c in (dataset.columns_meta or [])
        if c.get("excluded") or c["name"] in (model.excluded_cols or [])
    ]
    lines.append("## Исключённые колонки")
    if excluded:
        for c in excluded:
            reason = c.get("exclude_reason") or "исключена пользователем"
            lines.append(f"- `{c['name']}` — {reason}")
    else:
        lines.append("- все колонки использованы")
    lines.append("")

    lines.append("## Leakage Guard")
    verdict = (leakage_report or {}).get("verdict", "OK")
    lines.append(f"- Итоговый вердикт: **{verdict}**")
    if leakage_report.get("guard_override"):
        lines.append("- ⚠️ Блокировка снята пользователем осознанно — решение зафиксировано здесь")
    checks = []
    for part in ("pre", "split", "post"):
        checks.extend(((leakage_report or {}).get(part) or {}).get("checks") or [])
    for check in checks[:20]:
        mark = {"OK": "+", "WARN": "!", "BLOCK": "×"}.get(check.get("verdict"), "·")
        lines.append(f"- [{mark}] {check.get('detail')}")
    lines.append("")

    lines.append("## Схема валидации")
    split = manifest.get("split") or {}
    kind = split.get("kind", "random")
    kind_desc = {
        "out_of_time": "out-of-time: последние 20% по времени — holdout, дальше временная кросс-валидация",
        "group": "group split по сущности + отдельный калибровочный фолд",
        "random": "стратифицированный K-Fold + отдельный калибровочный фолд",
    }
    lines.append(f"- {kind_desc.get(kind, kind)}")
    lines.append(f"- Holdout: {split.get('n_holdout', '—')} объектов, калибровочный фолд: {split.get('n_calib', '—')}")
    lines.append(f"- Наивный baseline: {(split.get('baseline') or {}).get('detail', '—')}")
    lines.append("")

    lines.append("## Метрики против baseline")
    if task == "binary":
        lines.append(f"- ROC-AUC: **{metrics.get('roc_auc', '—')}** (baseline 0.5, lift {metrics.get('lift', '—')})")
        lines.append(f"- PR-AUC: {metrics.get('pr_auc', '—')} · LogLoss: {metrics.get('logloss', '—')} · Brier: {metrics.get('brier', '—')}")
        lines.append(f"- Precision/Recall на пороге 0.5: {metrics.get('precision', '—')} / {metrics.get('recall', '—')}")
    elif task == "multiclass":
        lines.append(f"- Accuracy: **{metrics.get('accuracy', '—')}** (baseline {metrics.get('baseline_accuracy', '—')})")
        lines.append(f"- Macro-F1: {metrics.get('macro_f1', '—')} · LogLoss: {metrics.get('logloss', '—')}")
    elif task == "timeseries":
        lines.append(f"- MAE: **{metrics.get('mae', '—')}** · RMSE: {metrics.get('rmse', '—')}" +
                    (f" · MAPE: {metrics.get('mape')}%" if metrics.get("mape") is not None else ""))
        lines.append(f"- Baseline (naive) MAE: {metrics.get('baseline_mae', '—')}")
    else:
        lines.append(f"- MAE: **{metrics.get('mae', '—')}** · RMSE: {metrics.get('rmse', '—')} · R²: {metrics.get('r2', '—')}")
        lines.append(f"- Baseline (медиана) MAE: {metrics.get('baseline_mae', '—')}")
    if metrics.get("coverage") is not None:
        lines.append(f"- Конформальное покрытие на holdout: {metrics.get('coverage')}% (цель {round(metrics.get('coverage_target', 0.9) * 100)}%)")
    lines.append("")

    calib = manifest.get("calibration")
    lines.append("## Калибровка вероятностей")
    lines.append(f"- Метод: {calib.get('kind') if calib else 'не требуется (не бинарная классификация)'}")
    if metrics.get("reliability"):
        lines.append("- Reliability-кривая доступна в UI на вкладке OVERVIEW")
    lines.append("")

    lines.append("## Бизнес-эффект")
    if threshold_info:
        lines.append(f"- Порог по прибыли: **{threshold_info.get('threshold')}** (вместо 0.5)")
        lines.append(f"- Прибыль за период: **{threshold_info.get('profit')} ₽** против «наугад» {threshold_info.get('profit_random')} ₽ и «обрабатывать всех» {threshold_info.get('profit_all')} ₽")
        lines.append(f"- Допущения: выгода TP {threshold_info.get('assumptions', {}).get('benefit_tp')} ₽, "
                     f"действие {threshold_info.get('assumptions', {}).get('action_cost')} ₽, "
                     f"пропуск {threshold_info.get('assumptions', {}).get('fn_cost')} ₽"
                     + (f", ёмкость {threshold_info.get('capacity')}" if threshold_info.get("capacity") else ""))
        lines.append(f"- Расчёт на {threshold_info.get('period_label', 'holdout-период')}, масштаб ×{threshold_info.get('scale', 1)}")
    else:
        lines.append("- Матрица стоимостей не задана — порог 0.5. Задайте выгоды и потери на вкладке PROFIT, чтобы получить порог по деньгам")
    lines.append("")

    lines.append("## Ограничения")
    lines.append("- What-if и контрфактуалы показывают ответ модели на изменение признака, а не доказанный причинный эффект")
    lines.append("- Конформальная гарантия покрытия — средняя (маргинальная) по данным, не для каждого объекта")
    lines.append("- Прибыль в рублях считается на допущениях пользователя о выгодах и потерях")
    if task == "timeseries":
        lines.append("- Прогноз временных рядов построен на лагах и скользящих статистиках, одна серия за раз; сильная сезонность вне календарных признаков не моделируется")
    lines.append("")

    lines.append("## Воспроизводимость")
    libs = manifest.get("libraries") or {}
    lines.append(f"- Seed: {manifest.get('seed')} · Режим: {manifest.get('mode')} · Детерминизм: {manifest.get('deterministic')}")
    if manifest.get("stopped_by_timer"):
        lines.append("- Поиск гиперпараметров остановлен по таймеру — взят лучший найденный кандидат")
    lines.append(f"- Библиотеки: " + ", ".join(f"{k} {v}" for k, v in libs.items()))
    lines.append(f"- Python: {manifest.get('python')}")
    return "\n".join(lines)
