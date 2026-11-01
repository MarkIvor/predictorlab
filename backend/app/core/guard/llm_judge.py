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
    return {"verdict": result.verdict if result.verdict in ("OK", "WARN", "BLOCK") else "WARN",
            "suspicious": result.suspicious[:20]}


def suggest_target(goal: str, columns_meta: list[dict], tables: list[dict] | None = None) -> dict | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_TARGET, prompts.user_target(goal, columns_meta, tables))
    return validate.parse(validate.TargetResult, data)


def suggest_features(config: dict, describes: dict) -> dict | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_FEATURES, prompts.user_features(config, describes))
    return validate.parse(validate.FeatureSuggestionResult, data)


def card_narrative(fields: dict) -> tuple[str, str] | None:
    if not llm_client.enabled():
        return None
    data = llm_client.chat_json(prompts.SYSTEM_CARD, prompts.user_card(fields))
    result = validate.parse(validate.CardResult, data)
    if result is None or not result.text:
        return None
    provided = [str(v) for v in fields.values()]
    ok, reason = validate.validate_card_text(result.text, provided)
    if not ok:
        return None, reason
    return result.text, ""
