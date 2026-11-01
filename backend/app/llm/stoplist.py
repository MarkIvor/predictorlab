"""Стоп-лист причинных слов: «из-за», «приводит к» и т.д. запрещены в находках ФАКТ/СВЯЗЬ."""

import re

CAUSAL_PATTERNS = [
    r"из[- ]за",
    r"приводит\s+к",
    r"вызывает",
    r"потому\s+что",
    r"вследствие",
    r"обусловлен[оа]?",
    r"является\s+причиной",
    r"повлиял[оа]?\s+на",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in CAUSAL_PATTERNS]


def validate_stoplist(text: str, label: str) -> bool:
    """True = текст допустим. False = содержит причинные слова при не-ПРИЧИННОМ ярлыке."""
    if label in ("ПРИЧИННАЯ", "ГИПОТЕЗА"):
        return True
    for pattern in _COMPILED:
        if pattern.search(text):
            return False
    return True
