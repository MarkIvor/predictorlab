from abc import ABC, abstractmethod

import pandas as pd


class Connector(ABC):
    db_type: str = "unknown"
    name: str = ""

    @abstractmethod
    def test(self) -> bool: ...

    @abstractmethod
    def list_tables(self) -> list[str]: ...

    @abstractmethod
    def fetch_table(self, table: str, limit: int = 500_000) -> pd.DataFrame: ...

    @abstractmethod
    def row_count(self, table: str) -> int: ...

    def execute_sql(self, sql: str, limit: int = 500_000) -> pd.DataFrame:
        raise NotImplementedError(f"{self.db_type} не поддерживает execute_sql")

    def quote(self, table: str) -> str:
        return f'"{table}"'

    def dialect(self) -> str:
        return self.db_type

    def foreign_keys(self, table: str) -> list[dict]:
        return []

    def describe(self, table: str) -> list[dict]:
        return [{"name": c, "type": "unknown"} for c in self.fetch_table(table, limit=1).columns]
