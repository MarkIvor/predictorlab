import hashlib
import io
import secrets
from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.core.ingest.typing import infer_column_meta
from app.services import pii as pii_service


class IngestError(Exception):
    def __init__(self, message: str, status: int = 400, hint: dict | None = None):
        super().__init__(message)
        self.status = status
        self.hint = hint or {}


def detect_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        match = from_bytes(raw[:256_000]).best()
        if match and match.encoding:
            return match.encoding
    except Exception:
        pass
    try:
        raw.decode("cp1251")
        return "cp1251"
    except UnicodeDecodeError:
        return "latin-1"


def sniff_separator(text: str) -> str:
    import csv
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|;")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in [",", ";", "\t", "|"]}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def read_csv_smart(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    encoding = detect_encoding(raw)
    head = raw[:256_000].decode(encoding, errors="replace")
    sep = sniff_separator(head)
    return pd.read_csv(path, sep=sep, encoding=encoding, low_memory=False)


def read_dataframe(path: Path, sheet: str | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_smart(path)
    if suffix in (".xlsx", ".xls"):
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True)
        sheets = book.sheetnames
        book.close()
        if sheet is None and len(sheets) > 1:
            raise IngestError(
                f"В файле несколько листов: {', '.join(sheets)}. Выберите лист для загрузки.",
                status=400, hint={"sheets": sheets},
            )
        return pd.read_excel(path, sheet_name=sheet or 0, engine="openpyxl")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise IngestError("Поддерживаются форматы CSV, XLSX и Parquet", status=400)


def sample_rows(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    settings = get_settings()
    if len(df) <= n:
        return df
    return df.sample(n=min(n, len(df)), random_state=seed).sort_index().reset_index(drop=True)


def ingest_dataframe(df: pd.DataFrame) -> tuple[str, int, int, list[dict], str, dict]:
    settings = get_settings()
    if df.shape[1] > settings.max_columns:
        raise IngestError(
            f"В данных {df.shape[1]} колонок — превышен лимит {settings.max_columns}. "
            "Удалите лишние колонки или поднимите лимит MAX_COLUMNS в .env",
            status=413, hint={"limit": settings.max_columns, "actual": int(df.shape[1])},
        )
    if len(df) > settings.max_rows:
        raise IngestError(
            f"В данных {len(df):,} строк — превышен лимит {settings.max_rows:,}. "
            "Загрузите выборку: укажите sample_rows (случайная) или сделайте стратифицированную выборку по таргету".replace(",", " "),
            status=413,
            hint={"limit": settings.max_rows, "actual": int(len(df)), "suggest_sampling": True},
        )
    df = df.where(df.notna(), None)
    columns_meta = infer_column_meta(df)
    preview = df.head(200).to_dict(orient="records")
    pii_map = pii_service.scan_columns(columns_meta, preview)
    for col in columns_meta:
        if col["name"] in pii_map:
            col["pii"] = pii_map[col["name"]]
            col["excluded"] = True
            col["exclude_reason"] = f"ПДн ({pii_service.PII_LABELS_RU.get(col['pii'], col['pii'])}) — исключено из обучения по умолчанию"

    dataset_id = f"ds_{secrets.token_hex(6)}"
    out_dir = settings.datasets_path / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    data_hash = hashlib.sha256(out_path.read_bytes()).hexdigest()

    duplicates = int(df.duplicated().sum())
    health = {
        "duplicates": duplicates,
        "constant_columns": [c["name"] for c in columns_meta if c["type"] == "constant"],
        "id_columns": [c["name"] for c in columns_meta if c["type"] == "id"],
        "pii_columns": {name: pii_service.PII_LABELS_RU.get(t, t) for name, t in pii_map.items()},
    }
    return dataset_id, len(df), df.shape[1], columns_meta, data_hash, health


def stratified_sample(df: pd.DataFrame, n: int, target_col: str, seed: int = 42) -> pd.DataFrame:
    if target_col not in df.columns:
        raise IngestError(f"Колонки «{target_col}» нет в данных", status=400)
    frac = min(1.0, n / max(len(df), 1))
    sampled = df.groupby(target_col, group_keys=False, dropna=False).apply(
        lambda g: g.sample(frac=frac, random_state=seed)
    )
    return sampled.sort_index().head(n).reset_index(drop=True)
