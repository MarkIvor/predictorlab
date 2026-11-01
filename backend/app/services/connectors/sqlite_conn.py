import os

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .base import Connector


class SQLiteConnector(Connector):
    db_type = "sqlite"

    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            db_path = self.params.get("database", "")
            if not os.path.isfile(db_path):
                raise FileNotFoundError(f"SQLite-файл не найден: {db_path}")
            self._engine = create_engine(f"sqlite:///{db_path}")
        return self._engine

    def test(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        with self.engine.connect() as c:
            rows = c.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
        return [r[0] for r in rows]

    def fetch_table(self, table: str, limit: int = 500_000) -> pd.DataFrame:
        q = self.quote(table)
        with self.engine.connect() as c:
            result = c.exec_driver_sql(f"SELECT * FROM {q} LIMIT {int(limit)}")
            return pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    def execute_sql(self, sql: str, limit: int = 500_000) -> pd.DataFrame:
        with self.engine.connect() as c:
            result = c.execute(text(sql))
            rows = result.fetchmany(int(limit))
            return pd.DataFrame(rows, columns=list(result.keys()))

    def row_count(self, table: str) -> int:
        try:
            with self.engine.connect() as c:
                row = c.execute(text(f"SELECT COUNT(*) FROM {self.quote(table)}")).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def describe(self, table: str) -> list[dict]:
        try:
            insp = inspect(self.engine)
            return [{"name": c["name"], "type": str(c.get("type", "unknown"))} for c in insp.get_columns(table)]
        except Exception:
            return super().describe(table)

    def foreign_keys(self, table: str) -> list[dict]:
        try:
            with self.engine.connect() as c:
                rows = c.execute(text(f"PRAGMA foreign_key_list('{table}')")).fetchall()
            return [{"column": r[3], "ref_table": r[2], "ref_column": r[4]} for r in rows]
        except Exception:
            return []
