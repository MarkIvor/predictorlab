from .sqlalchemy_base import SQLAlchemyConnector


class PostgresConnector(SQLAlchemyConnector):
    db_type = "postgresql"

    def _build_url(self) -> str:
        p = self.params
        user = p.get("username") or p.get("user", "")
        pwd = p.get("password", "")
        host = p.get("host", "localhost")
        port = p.get("port") or 5432
        db = p.get("database", "")
        return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

    def _default_schema(self) -> str | None:
        return "public"

    def _list_tables_sql(self, schema: str | None) -> str | None:
        return "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"

    def dialect(self) -> str:
        return "postgres"
