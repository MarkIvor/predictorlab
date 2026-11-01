import pandas as pd


def load_dataset_df(file_path: str, base_dir: object = None) -> pd.DataFrame:
    import duckdb

    path = file_path
    con = duckdb.connect()
    try:
        return con.execute(f"SELECT * FROM read_parquet('{_escape(path)}')").df()
    finally:
        con.close()


def query_dataset(file_path: str, sql: str) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW ds AS SELECT * FROM read_parquet('{_escape(file_path)}')")
        return con.execute(sql).df()
    finally:
        con.close()


def _escape(path: str) -> str:
    return path.replace("'", "''")
