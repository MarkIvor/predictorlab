import re

SYSTEM_JUDGE = (
    "Ты — строгий аудитор утечек целевой переменной в ML. Тебе дают ТОЛЬКО метаданные колонок "
    "(название, тип, статистики), без сырых строк. Верни JSON: "
    '{"suspicious": [{"column": "имя", "reason": "краткое объяснение по-русски"}], "verdict": "OK|WARN|BLOCK"}. '
    "Помечай колонки, которые могли быть известны только ПОСЛЕ наступления целевого события "
    "(статусы, даты закрытия/расторжения, результаты, флаги исхода). Если сомневаешься — WARN, не BLOCK."
)


def user_judge(columns_meta: list[dict], target_col: str, task_type: str) -> str:
    lines = [f"Таргет: {target_col}. Тип задачи: {task_type}. Колонки:"]
    for c in columns_meta[:200]:
        lines.append(f"- {c['name']} | тип: {c.get('type')} | уникальных: {c.get('nunique')} | пропуски: {c.get('missing_pct')}%")
    return "\n".join(lines)


SYSTEM_TARGET = (
    "Ты — data-инженер. Пользователь описывает цель прогноза словами. Тебе дают схему таблиц "
    "(имена колонок и типы). Верни JSON: "
    '{"target_col": "имя существующей колонки или null", "task_type": "binary|regression|multiclass", '
    '"sql": "SELECT-запрос разметки таргета или null", "explanation": "объяснение по-русски"}. '
    "SQL только SELECT, в диалекте DuckDB, с комментариями. Никаких INSERT/UPDATE."
)


def user_target(goal: str, columns_meta: list[dict], tables: list[dict] | None = None) -> str:
    lines = [f"Цель пользователя: {goal}", "Колонки датасета:"]
    for c in columns_meta[:200]:
        lines.append(f"- {c['name']} ({c.get('type')})")
    if tables:
        lines.append("Таблицы источника:")
        for t in tables[:30]:
            lines.append(f"- {t}")
    return "\n".join(lines)


SYSTEM_FEATURES = (
    "Ты — feature-инженер. Тебе дают схему таблиц БД и связи. Предложи до 7 доменных признаков. "
    'Верни JSON: {"features": [{"name": "имя_фичи", "description": "описание по-русски", '
    '"sql": "SELECT-выражение (DuckDB, без подзапросов изменения данных)"}]}. '
    "Используй только существующие колонки."
)


def user_features(config: dict, describes: dict) -> str:
    lines = ["Схема источника:"]
    for table, cols in (describes or {}).items():
        lines.append(f"Таблица {table}: " + ", ".join(f"{c['name']}({c['type']})" for c in cols[:40]))
    lines.append(f"Главная сущность: {config.get('main_table')}, ключ: {config.get('main_key')}")
    for child in config.get("children", []):
        lines.append(f"Дочерняя: {child['table']} (fk: {child.get('fk')}, время: {child.get('datetime_col')})")
    return "\n".join(lines)


SYSTEM_CARD = (
    "Ты — бизнес-аналитик. Тебе дают посчитанные поля Model Card. Напиши живой текст по-русски: "
    "3-5 абзацев — что модель умеет, кому полезна, какие главные драйверы, как читать метрики. "
    "ЗАПРЕЩЕНО: придумывать новые числа, округлять иначе, добавлять проценты, которых нет во входных данных. "
    'Используй только числа, которые есть в полях. Верни JSON: {"text": "..."}.'
)


def user_card(fields: dict) -> str:
    return "Посчитанные поля:\n" + "\n".join(f"{k}: {v}" for k, v in fields.items())


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", text)
