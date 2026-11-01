import re

from pydantic import BaseModel, Field, ValidationError


class JudgeResult(BaseModel):
    suspicious: list[dict] = Field(default_factory=list)
    verdict: str = "OK"


class TargetResult(BaseModel):
    target_col: str | None = None
    task_type: str | None = None
    sql: str | None = None
    explanation: str = ""


class FeatureSuggestionResult(BaseModel):
    features: list[dict] = Field(default_factory=list)


class CardResult(BaseModel):
    text: str = ""


def parse(model_cls, data):
    if data is None:
        return None
    try:
        return model_cls(**data)
    except (ValidationError, TypeError):
        return None


def validate_card_text(text: str, provided_values: list[str]) -> tuple[bool, str]:
    """Все числа в тексте LLM должны присутствовать во входных данных (13.3)."""
    text_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", text))
    allowed = set()
    for v in provided_values:
        allowed.update(re.findall(r"\d+(?:[.,]\d+)?", str(v)))
    unknown = text_numbers - allowed
    if unknown:
        return False, f"Числа не из исходных данных: {', '.join(sorted(unknown)[:10])}"
    return True, ""
