from typing import Any

from app.llm import client as llm_client
from app.llm import prompts, validate


def judge_columns(columns_meta: list[dict], target_col: str, task_type: str) -> dict | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(
        prompts.SYSTEM_JUDGE,
        prompts.user_judge(columns_meta, target_col, task_type),
    )
    result = validate.parse(validate.JudgeResult, data)
    if result is None:
        return None
    return {"verdict": result.verdict if result.verdict in ("OK", "WARN", "BLOCK") else "WARN", "suspicious": result.suspicious[:20]}


def suggest_target(goal: str, columns_meta: list[dict], tables: list[dict] | None = None) -> Any | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_TARGET, prompts.user_target(goal, columns_meta, tables))
    return validate.parse(validate.TargetResult, data)


def suggest_features(config: dict, describes: dict) -> dict | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_FEATURES, prompts.user_features(config, describes))
    parsed = validate.parse(validate.FeatureSuggestionResult, data)
    if parsed is None:
        return None
    if hasattr(parsed, "model_dump"):
        return dict(parsed.model_dump())
    return None


def card_narrative(fields: dict) -> tuple[str, str] | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_CARD, prompts.user_card(fields))
    result = validate.parse(validate.CardResult, data)
    if result is None or not result.text:
        return None
    provided = [str(v) for v in fields.values()]
    ok, reason = validate.validate_card_text(result.text, provided)
    del reason
    if not ok:
        return None
    return result.text, ""
