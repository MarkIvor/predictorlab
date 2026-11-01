import pandas as pd

from .base import Connector


class ClickHouseConnector(Connector):
    db_type = "clickhouse"

    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import clickhouse_connect
            p = self.params
            self._client = clickhouse_connect.get_client(
                host=p.get("host", "localhost"),
                port=int(p.get("port") or 8123),
                username=p.get("username", "default"),
                password=p.get("password", ""),
                database=p.get("database", "default"),
            )
        return self._client

    def test(self) -> bool:
        try:
            self.client.command("SELECT 1")
            return True
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        try:
            res = self.client.command("SHOW TABLES")
            if isinstance(res, str):
                return [t.strip() for t in res.strip().split("\n") if t.strip()]
            if hasattr(res, "result_rows"):
                return [r[0] for r in res.result_rows]
            return list(res) if res else []
        except Exception:
            return []

    def fetch_table(self, table: str, limit: int = 500_000) -> pd.DataFrame:
        return self.client.query_df(f"SELECT * FROM `{table}` LIMIT {int(limit)}")

    def execute_sql(self, sql: str, limit: int = 500_000) -> pd.DataFrame:
        return self.client.query_df(sql, settings={"max_execution_time": 120})

    def row_count(self, table: str) -> int:
        try:
            r = self.client.command(f"SELECT COUNT(*) FROM `{table}`")
            return int(r) if r is not None else 0
        except Exception:
            return 0

    def describe(self, table: str) -> list[dict]:
        try:
            df = self.client.query_df(f"DESCRIBE TABLE `{table}`")
            name_col = "name" if "name" in df.columns else df.columns[0]
            type_col = "type" if "type" in df.columns else df.columns[1]
            return [{"name": str(r[name_col]), "type": str(r[type_col])} for _, r in df.iterrows()]
        except Exception:
            return super().describe(table)

    def dialect(self) -> str:
        return "clickhouse"
