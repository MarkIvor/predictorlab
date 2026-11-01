from typing import Any


def require(value: Any, message: str) -> Any:
    """Сужает Optional до значения: поднимает RuntimeError, если None."""
    if value is None:
        raise RuntimeError(message)
    return value
