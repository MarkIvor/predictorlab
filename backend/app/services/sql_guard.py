_BLOCKED_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "TRUNCATE",
    "ALTER",
    "CREATE",
    "GRANT",
    "REVOKE",
    "MERGE",
    "CALL",
    "VACUUM",
    "REINDEX",
    "REFRESH",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "COPY",
    "BULK",
    "LOAD",
    "IMPORT",
}

_ALLOWED_KEYWORDS = {"SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE", "DESC", "VALUES"}


def check_read_only(sql: str) -> tuple[bool, str]:
    sql_stripped = (sql or "").strip()
    if not sql_stripped:
        return True, ""
    statements = [s for s in sql_stripped.split(";") if s.strip()]
    for stmt in statements:
        first_word = stmt.strip().split()[0].upper() if stmt.strip().split() else ""
        if first_word not in _ALLOWED_KEYWORDS:
            return False, (f"Подключения к БД работают в read-only: оператор «{first_word}» запрещён. Разрешены только SELECT/WITH/EXPLAIN/SHOW/DESCRIBE")
    upper = sql_stripped.upper()
    for kw in ("INSERT INTO", "INSERT ", "UPDATE ", "DELETE FROM", "DROP ", "TRUNCATE ", "ALTER ", "CREATE "):
        if kw in upper:
            return False, (f"Подключения к БД работают в read-only: обнаружен оператор изменения данных «{kw.strip()}». Разрешены только SELECT-запросы")
    return True, ""
