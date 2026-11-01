from app.core.registry.modelcard import build_card_md
from app.llm.validate import validate_card_text


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def make_model():
    import datetime
    model = _Obj(
        name="Test Churn", task_type="binary", target_col="churn", excluded_cols=["email"],
        status="ready", guard_verdict="OK",
    )
    dataset = _Obj(
        name="demo", nrows=24000, ncols=17, event_time_col="event_date",
        data_hash="a" * 64, columns_meta=[{"name": "email", "excluded": True, "exclude_reason": "ПДн (Email)"}],
    )
    version = _Obj(version=1, created_at=datetime.datetime(2026, 11, 1), metrics={}, leakage_report={})
    metrics = {
        "roc_auc": 0.87, "pr_auc": 0.5, "logloss": 0.31, "brier": 0.08,
        "precision": 0.6, "recall": 0.5, "lift": 0.37, "coverage": 0.91, "coverage_target": 0.9,
        "baseline": {"detail": "baseline"}, "drivers": [{"feature": "days_since"}],
    }
    manifest = {
        "split": {"kind": "out_of_time", "n_holdout": 4800, "n_calib": 2400,
                  "baseline": {"detail": "Наивный baseline: всегда предсказывать «1»"}},
        "calibration": {"kind": "isotonic"},
        "mode": "quick", "seed": 42, "deterministic": False, "python": "3.12", "libraries": {"catboost": "1.2"},
    }
    return model, dataset, version, metrics, manifest


def test_card_sections_present():
    model, dataset, version, metrics, manifest = make_model()
    card = build_card_md(model, dataset, version, metrics, manifest, {"verdict": "OK", "checks": []}, None)
    for section in ("Model Card", "Назначение", "Данные", "Исключённые колонки", "Leakage Guard",
                    "Схема валидации", "Метрики против baseline", "Ограничения", "Воспроизводимость"):
        assert section in card
    assert "out-of-time" in card
    assert "0.87" in card
    assert "ПДн (Email)" in card


def test_card_profit_section():
    model, dataset, version, metrics, manifest = make_model()
    info = {"threshold": 0.11, "profit": 150000, "profit_random": 20000, "profit_all": 10000,
            "assumptions": {"benefit_tp": 40000, "action_cost": 1500, "fn_cost": 8000, "n_holdout": 4800},
            "period_label": "holdout = 1 месяц", "scale": 1}
    card = build_card_md(model, dataset, version, metrics, manifest, {"verdict": "OK", "checks": []}, info)
    assert "0.11" in card
    assert "150000" in card
    assert "Матрица стоимостей не задана" not in card


def test_llm_number_validator():
    ok, _ = validate_card_text("Модель даёт +1.84M ₽ и AUC 0.87", ["1.84", "0.87"])
    assert ok
    bad, reason = validate_card_text("Прибыль составила 999999 рублей", ["1.84", "0.87"])
    assert not bad
    assert "999999" in reason
