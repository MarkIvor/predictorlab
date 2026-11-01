import numpy as np
import pandas as pd

VALID_TYPES = ("numeric", "categorical", "datetime", "text", "boolean", "id", "constant")
DATETIME_PARTS = ("year", "month", "day", "hour", "dayofweek", "dayofyear")


def build_feature_spec(columns_meta: list[dict], target_col: str, excluded_cols: list[str]) -> dict:
    excluded = set(excluded_cols) | {target_col}
    numeric: list[str] = []
    categorical: list[str] = []
    boolean: list[str] = []
    datetime_cols: dict[str, list[str]] = {}
    text: list[str] = []

    for col in columns_meta:
        name = col["name"]
        if name in excluded or col.get("excluded"):
            continue
        ctype = col.get("type")
        if ctype == "numeric":
            numeric.append(name)
        elif ctype == "categorical":
            categorical.append(name)
        elif ctype == "boolean":
            boolean.append(name)
        elif ctype == "datetime":
            datetime_cols[name] = list(DATETIME_PARTS)
        elif ctype == "text":
            text.append(name)

    feature_cols = numeric + boolean + [f"{c}__{p}" for c, parts in datetime_cols.items() for p in parts] + categorical
    return {
        "numeric": numeric,
        "boolean": boolean,
        "datetime": datetime_cols,
        "categorical": categorical,
        "text": text,
        "feature_cols": feature_cols,
        "target_col": target_col,
    }


def source_columns(spec: dict) -> list[str]:
    return list(spec.get("numeric", [])) + list(spec.get("boolean", [])) + list(spec.get("datetime", {}).keys()) + list(spec.get("categorical", []))


def transform(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in spec.get("numeric", []):
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
    for col in spec.get("boolean", []):
        if col in df.columns:
            out[col] = _to_bool(df[col])
    for col, parts in spec.get("datetime", {}).items():
        if col not in df.columns:
            continue
        dt = pd.to_datetime(df[col], errors="coerce")
        for part in parts:
            if part == "year":
                out[f"{col}__year"] = dt.dt.year.astype(float)
            elif part == "month":
                out[f"{col}__month"] = dt.dt.month.astype(float)
            elif part == "day":
                out[f"{col}__day"] = dt.dt.day.astype(float)
            elif part == "hour":
                out[f"{col}__hour"] = dt.dt.hour.astype(float)
            elif part == "dayofweek":
                out[f"{col}__dayofweek"] = dt.dt.dayofweek.astype(float)
            elif part == "dayofyear":
                out[f"{col}__dayofyear"] = dt.dt.dayofyear.astype(float)
    for col in spec.get("categorical", []):
        if col in df.columns:
            out[col] = df[col].astype("object").where(df[col].notna(), "__nan__").astype(str)
    for col in out.columns:
        if col not in spec.get("categorical", []):
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _to_bool(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.lower()
    mapping = {
        "true": 1.0,
        "yes": 1.0,
        "y": 1.0,
        "да": 1.0,
        "1": 1.0,
        "t": 1.0,
        "истина": 1.0,
        "false": 0.0,
        "no": 0.0,
        "n": 0.0,
        "нет": 0.0,
        "0": 0.0,
        "f": 0.0,
        "ложь": 0.0,
    }
    result = s.map(mapping)
    return result.where(series.notna(), np.nan)


def encode_target(series: pd.Series, task_type: str) -> tuple[np.ndarray, dict]:
    if task_type in ("binary", "multiclass"):
        classes = sorted(series.dropna().unique(), key=str)
        mapping = {str(c): i for i, c in enumerate(classes)}
        y = series.map(lambda v: mapping.get(str(v))).to_numpy(dtype=float)
        y = y[~np.isnan(y)]
        return y, {"classes": [str(c) for c in classes], "mapping": mapping}
    y = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return y, {}
