import pandas as pd

BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "да", "нет", "1", "0", "t", "f", "истина", "ложь"}


def _try_numeric(series: pd.Series) -> float:
    if pd.api.types.is_numeric_dtype(series):
        return 1.0
    converted = pd.to_numeric(series, errors="coerce")
    non_null = series.notna()
    if non_null.sum() == 0:
        return 0.0
    return float(converted[non_null].notna().mean())


def _try_datetime(series: pd.Series) -> float:
    if pd.api.types.is_datetime64_any_dtype(series):
        return 1.0
    if pd.api.types.is_numeric_dtype(series):
        return 0.0
    non_null = series.dropna().head(200)
    if non_null.empty:
        return 0.0
    date_like_count = sum(1 for v in non_null.tolist() if _date_like(str(v)))
    if date_like_count < max(1, int(len(non_null) * 0.5)):
        return 0.0
    try:
        converted = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    except (ValueError, TypeError):
        return 0.0
    mask = series.notna()
    if mask.sum() == 0:
        return 0.0
    return float(converted[mask].notna().mean())


def _date_like(value: str) -> bool:
    import re

    return bool(re.search(r"\d{1,4}[-/.:T]\d{1,2}", value)) or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value))


def infer_column_meta(df: pd.DataFrame, scan_rows: int = 50_000) -> list[dict]:
    sample_df = df.head(scan_rows)
    n = len(df)
    meta: list[dict] = []
    for name in df.columns:
        col = df[name]
        col_sample = sample_df[name].dropna()
        n_missing = int(col.isna().sum())
        non_null = n - n_missing
        nunique = int(col.nunique(dropna=True))
        uniqueness = (nunique / non_null) if non_null else 0.0
        sample_values = [str(v) for v in col_sample.head(5).tolist()]

        col_type = "text"
        if non_null == 0:
            col_type = "constant"
        elif nunique <= 1:
            col_type = "constant"
        elif nunique == 2 and set(str(v).lower() for v in col_sample.unique()) <= BOOL_TOKENS:
            col_type = "boolean"
        elif _try_datetime(col) >= 0.95:
            col_type = "datetime"
        elif _try_numeric(col) >= 0.95:
            col_type = "numeric"
        elif uniqueness >= 0.95:
            col_type = "id"
        elif (nunique / max(non_null, 1)) <= 0.05 or nunique <= 30:
            col_type = "categorical"

        stats: dict = {}
        if col_type == "numeric":
            num = pd.to_numeric(col, errors="coerce")
            stats = {
                "mean": None if num.dropna().empty else round(float(num.mean()), 6),
                "min": None if num.dropna().empty else float(num.min()),
                "max": None if num.dropna().empty else float(num.max()),
            }
        elif col_type in ("categorical", "boolean"):
            top = col.value_counts(dropna=True).head(5)
            stats = {"top": [{"value": str(k), "count": int(v)} for k, v in top.items()]}

        meta.append(
            {
                "name": str(name),
                "type": col_type,
                "pandas_dtype": str(col.dtype),
                "n_missing": n_missing,
                "missing_pct": round(n_missing / n * 100, 3) if n else 0.0,
                "nunique": nunique,
                "uniqueness": round(uniqueness, 6),
                "sample": sample_values,
                "stats": stats,
                "pii": None,
                "excluded": col_type in ("id", "constant"),
                "exclude_reason": "ID-подобная колонка" if col_type == "id" else ("константа" if col_type == "constant" else None),
            }
        )
    return meta
