from app.services import pii


def test_detect_email_by_name_and_value():
    assert pii.detect_pii_type("client_email", ["a@b.ru"]) == "email"
    assert pii.detect_pii_type("email", []) == "email"


def test_detect_phone_inn_snils_passport_card():
    assert pii.detect_pii_type("contact", ["+7 912 345-67-89"]) == "phone"
    assert pii.detect_pii_type("code", ["7707083893"]) == "inn"
    assert pii.detect_pii_type("doc", ["112-233-445 95"]) == "snils"
    assert pii.detect_pii_type("doc", ["45 08 123456"]) == "passport"
    assert pii.detect_pii_type("pay", ["4111 1111 1111 1111"]) == "card"


def test_clean_columns_not_flagged():
    assert pii.detect_pii_type("revenue", ["123.45"]) == ""
    assert pii.detect_pii_type("segment", ["SMB"]) == ""


def test_scan_columns():
    columns = [{"name": "client_email"}, {"name": "amount"}]
    rows = [{"client_email": "x@y.ru", "amount": 10}, {"client_email": "z@w.ru", "amount": 20}]
    result = pii.scan_columns(columns, rows)
    assert result == {"client_email": "email"}


def test_mask_values():
    assert "***" in pii.mask_value("user@corp.ru", "email")
    assert "***" in pii.mask_value("+7 912 345-67-89", "phone")
    masked = pii.mask_record({"email": "a@b.ru", "sum": 5}, {"email": "email"})
    assert masked["sum"] == 5
    assert "@" in masked["email"] and "***" in masked["email"]
