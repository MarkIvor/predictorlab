import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)
_WINDOW = 60.0


def allow(key: str, limit: int, window: float = _WINDOW) -> bool:
    if limit <= 0:
        return True
    now = time.monotonic()
    with _lock:
        dq = _hits[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


def remaining(key: str, limit: int, window: float = _WINDOW) -> int:
    now = time.monotonic()
    with _lock:
        dq = _hits[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        return max(0, limit - len(dq))
