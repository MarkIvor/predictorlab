import re
from typing import Any

PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("phone", re.compile(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")),
    ("inn", re.compile(r"\b\d{10,12}\b")),
    ("snils", re.compile(r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b")),
    ("passport", re.compile(r"\b\d{2}\s?\d{2}\s?\d{6}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
]

PII_COLUMN_NAMES: dict[str, str] = {
    "email": "email",
    "e_mail": "email",
    "почта": "email",
    "phone": "phone",
    "tel": "phone",
    "mobile": "phone",
    "телефон": "phone",
    "inn": "inn",
    "инн": "inn",
    "snils": "snils",
    "снилс": "snils",
    "passport": "passport",
    "паспорт": "passport",
    "card_number": "card",
    "credit_card": "card",
    "карта": "card",
    "full_name": "name",
    "first_name": "name",
    "last_name": "name",
    "фио": "name",
    "birth_date": "birthdate",
    "birthday": "birthdate",
    "дата_рождения": "birthdate",
}

PII_LABELS_RU = {
    "email": "Email",
    "phone": "Телефон",
    "inn": "ИНН",
    "snils": "СНИЛС",
    "passport": "Паспорт",
    "card": "Номер карты",
    "name": "ФИО",
    "birthdate": "Дата рождения",
    "address": "Адрес",
}

SCAN_ROWS = 200


def detect_pii_type(column_name: str, sample_values: list[Any]) -> str:
    cn_lower = str(column_name).lower().replace(" ", "_").replace("-", "_")
    for pattern, pii_type in PII_COLUMN_NAMES.items():
        if pattern in cn_lower:
            return pii_type
    for val in (sample_values or [])[:SCAN_ROWS]:
        if val is None:
            continue
        s = str(val)
        for pii_type, regex in PII_PATTERNS:
            if regex.search(s):
                return pii_type
    return ""


def scan_columns(columns: list[dict], sample_rows: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for col in columns:
        name = col["name"]
        samples = [r.get(name) for r in sample_rows]
        pii_type = detect_pii_type(name, samples)
        if pii_type:
            result[name] = pii_type
    return result


def mask_value(value: Any, pii_type: str) -> Any:
    if value is None:
        return ""
    if not pii_type:
        return value
    s = str(value)
    if pii_type == "email":
        at = s.find("@")
        if at > 1:
            return s[0] + "***@" + s[at + 1 :]
        return "***@" + s
    if pii_type == "phone":
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 4:
            return f"+{digits[0]}({digits[1:4]})***-**-{digits[-2:]}"
        return "***"
    if pii_type == "inn":
        return s[:4] + "******" if len(s) >= 4 else "***"
    if pii_type in ("snils", "passport"):
        return ("***-***-" + s[-2:]) if len(s) >= 2 else "***"
    if pii_type == "card":
        return ("**** **** **** " + s[-4:]) if len(s) >= 4 else "****"
    if pii_type in ("name", "birthdate", "address"):
        return "***"
    return s[:1] + "***" if s else s


def mask_record(record: dict, pii_map: dict[str, str]) -> dict:
    if not pii_map:
        return record
    out = {}
    for k, v in record.items():
        out[k] = mask_value(v, pii_map[k]) if (k in pii_map and v is not None) else v
    return out
