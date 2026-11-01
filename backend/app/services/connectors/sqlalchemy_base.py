import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .base import Connector


class SQLAlchemyConnector(Connector):
    db_type = "sqlalchemy"

    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        self._engine: Engine | None = None

    def _build_url(self) -> str:
        raise NotImplementedError

    def _default_schema(self) -> str | None:
        return None

    def _list_tables_sql(self, schema: str | None) -> str | None:
        return None

    def dialect(self) -> str:
        return self.db_type

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(self._build_url(), pool_pre_ping=True)
        return self._engine

    def test(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        sql = self._list_tables_sql(None)
        if sql:
            try:
                with self.engine.connect() as c:
                    rows = c.execute(text(sql)).fetchall()
                return [r[0] for r in rows]
            except Exception:
                pass
        try:
            insp = inspect(self.engine)
            schema = self._default_schema()
            return insp.get_table_names(schema=schema)
        except Exception:
            return []

    def fetch_table(self, table: str, limit: int = 500_000) -> pd.DataFrame:
        q = self.quote(table)
        with self.engine.connect() as c:
            result = c.execution_options(stream_results=True, max_row_buffer=50_000).exec_driver_sql(f"SELECT * FROM {q} LIMIT {int(limit)}")
            return pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    def execute_sql(self, sql: str, limit: int = 500_000) -> pd.DataFrame:
        with self.engine.connect() as c:
            c = c.execution_options(timeout=120)
            result = c.execute(text(sql))
            rows = result.fetchmany(int(limit))
            return pd.DataFrame(rows, columns=list(result.keys()))

    def row_count(self, table: str) -> int:
        q = self.quote(table)
        try:
            with self.engine.connect() as c:
                row = c.execute(text(f"SELECT COUNT(*) FROM {q}")).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def describe(self, table: str) -> list[dict]:
        try:
            insp = inspect(self.engine)
            schema = self._default_schema()
            cols_info = insp.get_columns(table, schema=schema) if schema else insp.get_columns(table)
            return [{"name": c["name"], "type": str(c.get("type", "unknown"))} for c in cols_info]
        except Exception:
            return super().describe(table)

    def foreign_keys(self, table: str) -> list[dict]:
        try:
            insp = inspect(self.engine)
            schema = self._default_schema()
            fks = insp.get_foreign_keys(table, schema=schema) if schema else insp.get_foreign_keys(table)
            result = []
            for fk in fks:
                result.append(
                    {
                        "column": (fk.get("constrained_columns") or [""])[0],
                        "ref_table": fk.get("referred_table", ""),
                        "ref_column": (fk.get("referred_columns") or [""])[0],
                    }
                )
            return [r for r in result if r["column"] and r["ref_table"]]
        except Exception:
            return []
