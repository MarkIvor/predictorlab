import pytest
from app.llm import validate
from app.llm.prompts import SYSTEM_CARD, SYSTEM_JUDGE

pytestmark = pytest.mark.llm


def test_number_validator_accepts_known_numbers() -> None:
    ok, _ = validate.validate_card_text("Прибыль составила 1.84M ₽ при AUC 0.87", ["1.84", "0.87"])
    assert ok


def test_number_validator_rejects_unknown_numbers() -> None:
    ok, reason = validate.validate_card_text("Прибыль 999999 рублей", ["1.84", "0.87"])
    assert not ok
    assert "999999" in reason


def test_stoplist_validator_rejects_causal_words() -> None:
    assert not validate.validate_stoplist("Отток вырос из-за скидки", "СВЯЗЬ")
    assert not validate.validate_stoplist("Скидка приводит к оттоку", "ФАКТ")
    assert not validate.validate_stoplist("Промо вызывает рост", "ФАКТ")


def test_stoplist_validator_allows_for_causal_label() -> None:
    assert validate.validate_stoplist("Скидка из-за промо повлияла", "ПРИЧИННАЯ")


def test_stoplist_validator_allows_descriptive_text() -> None:
    assert validate.validate_stoplist("В сегменте отток 31.2%", "ФАКТ")
    assert validate.validate_stoplist("Признак коррелирует с таргетом", "СВЯЗЬ")


def test_judge_schema_parses_valid_json() -> None:
    result = validate.parse(validate.JudgeResult, {"verdict": "OK", "suspicious": []})
    assert result is not None
    assert result.verdict == "OK"


def test_judge_schema_rejects_garbage() -> None:
    result = validate.parse(validate.JudgeResult, {"garbage": True})
    assert result is not None
    assert result.verdict == "OK"
    assert result.suspicious == []


def test_judge_schema_rejects_none() -> None:
    assert validate.parse(validate.JudgeResult, None) is None


def test_target_schema_valid() -> None:
    data = {"target_col": "churn", "task_type": "binary", "sql": "SELECT 1", "explanation": "тест"}
    result = validate.parse(validate.TargetResult, data)
    assert result is not None
    assert result.target_col == "churn"


def test_target_schema_partial() -> None:
    result = validate.parse(validate.TargetResult, {"explanation": "не нашли"})
    assert result is not None
    assert result.target_col is None
    assert result.explanation == "не нашли"


def test_prompts_contain_json_instruction() -> None:
    assert "JSON" in SYSTEM_JUDGE
    assert "JSON" in SYSTEM_CARD


def test_raw_data_never_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.guard import llm_judge as judge_module

    captured = []

    def fake_chat_json(system: str, user: str, retries: int = 2, timeout: float = 60.0) -> dict | None:
        captured.append({"system": system, "user": user})
        return {"verdict": "OK", "suspicious": []}

    monkeypatch.setattr(judge_module.llm_client, "chat_json", fake_chat_json)
    monkeypatch.setattr(judge_module.llm_client, "enabled", lambda: True)

    columns_meta = [
        {"name": "email_col", "type": "text", "sample": ["MARKER_RAW_ROW_777@secret.com"]},
        {"name": "amount", "type": "numeric", "sample": ["123.45"]},
    ]
    result = judge_module.judge_columns(columns_meta, "target", "binary")
    assert result is not None
    full_prompt = " ".join(c["user"] for c in captured)
    assert "MARKER_RAW_ROW_777" not in full_prompt, "сырые строки данных не должны уходить в LLM!"
    assert "amount" in full_prompt
