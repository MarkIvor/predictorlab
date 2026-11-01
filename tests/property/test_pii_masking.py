import pytest
from app.services.pii import detect_pii_type, mask_value
from hypothesis import given, settings
from hypothesis import strategies as st

pytestmark = pytest.mark.property


@settings(max_examples=50, deadline=None)
@given(inn=st.integers(min_value=10**9, max_value=10**10 - 1))
def test_inn_never_survives_masking(inn: int) -> None:
    raw = str(inn)
    assert detect_pii_type("code", [raw]) == "inn"
    masked = mask_value(raw, "inn")
    assert masked != raw, "маскированный ИНН не должен совпадать с исходным"
    assert raw not in masked or len(masked) < len(raw)


@settings(max_examples=50, deadline=None)
@given(
    area=st.integers(min_value=100, max_value=999),
    group=st.integers(min_value=100, max_value=999),
    subj=st.integers(min_value=100, max_value=999),
    check=st.integers(min_value=10, max_value=99),
)
def test_snils_never_survives_masking(area: int, group: int, subj: int, check: int) -> None:
    raw = f"{area}-{group}-{subj} {check:02d}"
    masked = mask_value(raw, "snils")
    assert masked != raw
    assert raw not in masked or len(masked) < len(raw)


@settings(max_examples=50, deadline=None)
@given(
    local=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=3, max_size=10),
    domain=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8),
)
def test_email_never_survives_masking(local: str, domain: str) -> None:
    raw = f"{local}@{domain}.com"
    masked = mask_value(raw, "email")
    assert raw != masked, f"email должен маскироваться: {raw}"
    assert "***" in masked, f"маскированный email должен содержать ***: {masked}"
    at_pos = masked.find("@")
    assert at_pos > 0, "маскированный email должен содержать @"
    local_masked = masked[:at_pos]
    assert local not in local_masked or len(local_masked) < len(local), f"локальная часть '{local}' видна в '{local_masked}'"


@settings(max_examples=50, deadline=None)
@given(value=st.floats(min_value=-1000000, max_value=1000000))
def test_non_pii_value_unchanged(value: float) -> None:
    masked = mask_value(value, "")
    assert masked == value, f"значение без ПДн не должно маскироваться: {value} → {masked}"


@settings(max_examples=30, deadline=None)
@given(
    d1=st.integers(min_value=1, max_value=31),
    m1=st.integers(min_value=1, max_value=12),
    y1=st.integers(min_value=1900, max_value=2100),
)
def test_birthday_never_survives_masking(d1: int, m1: int, y1: int) -> None:
    raw = f"{y1:04d}-{m1:02d}-{d1:02d}"
    masked = mask_value(raw, "birthdate")
    assert masked == "***", "дата рождения должна полностью маскироваться"
