from app.services.sql_guard import check_read_only


def test_select_allowed():
    ok, _ = check_read_only("SELECT * FROM orders")
    assert ok


def test_with_select_allowed():
    ok, _ = check_read_only("WITH x AS (SELECT 1) SELECT * FROM x")
    assert ok


def test_insert_blocked():
    ok, _ = check_read_only("INSERT INTO orders VALUES (1)")
    assert not ok


def test_update_delete_drop_blocked():
    for sql in (
        "UPDATE orders SET a = 1",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "TRUNCATE orders",
        "ALTER TABLE orders ADD COLUMN x INT",
        "CREATE TABLE t (a int)",
    ):
        ok, _ = check_read_only(sql)
        assert not ok, sql


def test_cte_hiding_insert_blocked():
    ok, _ = check_read_only("WITH x AS (INSERT INTO t VALUES (1)) SELECT * FROM x")
    assert not ok


def test_multi_statement_blocked():
    ok, _ = check_read_only("SELECT 1; DROP TABLE orders")
    assert not ok


def test_lowercase_blocked():
    ok, _ = check_read_only("delete from orders")
    assert not ok


def test_show_and_describe_allowed():
    for sql in ("SHOW TABLES", "DESCRIBE orders"):
        ok, _ = check_read_only(sql)
        assert ok
