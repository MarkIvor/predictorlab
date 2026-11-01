from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import roc_auc_score

GUARD_YAML = Path(__file__).parent / "guard.yaml"


def load_config() -> dict:
    with open(GUARD_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return dict(cfg)


def _check(id: str, verdict: str, detail: str, **extra: object) -> dict:
    return {"id": id, "verdict": verdict, "detail": detail, **extra}  # type: ignore[typeddict-item]


def _auc_safe(y: np.ndarray, x: np.ndarray) -> float | None:
    mask = ~(np.isnan(x) | pd.isna(y))
    y_m, x_m = np.asarray(y)[mask], np.asarray(x)[mask]
    if len(y_m) < 50 or len(np.unique(y_m)) < 2 or len(np.unique(x_m)) < 2:
        return None
    try:
        auc = roc_auc_score(y_m.astype(int), x_m.astype(float))
        return float(max(auc, 1 - auc))
    except Exception:
        return None


def run_pre_checks(
    df: pd.DataFrame, target_col: str, task_type: str, event_time_col: str | None, entity_col: str | None, columns_meta: list[dict], excluded_cols: list[str]
) -> dict:
    cfg = load_config()
    checks: list[dict] = []
    exclude_auto: dict[str, str] = {}

    if len(df) < cfg["min_rows"]:
        checks.append(_check("min_rows", "WARN", f"Всего {len(df)} строк — модели будет тесно, интервалы широкими"))
    if target_col not in df.columns:
        return {
            "verdict": "BLOCK",
            "checks": [_check("target_missing", "BLOCK", f"Колонки «{target_col}» нет в данных")],
            "exclude_auto": {},
            "warnings_text": "",
        }

    target = df[target_col]
    meta_by_name = {c["name"]: c for c in columns_meta}

    if task_type == "binary":
        classes = target.dropna().unique()
        if len(classes) != 2:
            checks.append(_check("binary_classes", "BLOCK", f"Для бинарной классификации нужно 2 класса, найдено {len(classes)}"))
        else:
            counts = target.value_counts()
            minority = counts.min()
            if minority < cfg["min_class_count"]:
                checks.append(_check("class_imbalance", "WARN", f"Меньший класс содержит всего {minority} объектов — возможен дисбаланс"))

    excluded_set = set(excluded_cols)
    feature_cols = [c for c in df.columns if c != target_col and c not in excluded_set]

    suspicious = [str(p).lower() for p in cfg["suspicious_names"]]
    for col in feature_cols:
        cn = col.lower()
        if any(p in cn for p in suspicious):
            checks.append(
                _check("suspicious_name", "WARN", f"Название колонки «{col}» похоже на признак, который становится известен только после события", column=col)
            )

    if event_time_col and event_time_col in df.columns:
        ev = pd.to_datetime(df[event_time_col], errors="coerce")
        for col in feature_cols:
            meta = meta_by_name.get(col, {})
            if meta.get("type") != "datetime" or col == event_time_col:
                continue
            col_dt = pd.to_datetime(df[col], errors="coerce")
            both = ev.notna() & col_dt.notna()
            if both.sum() < 50:
                continue
            share = float((col_dt[both] >= ev[both]).mean())
            if share > cfg["future_feature_share"]:
                checks.append(
                    _check(
                        "future_feature", "BLOCK", f"Колонка «{col}» содержит даты позже времени события ({share:.0%} строк) — признак из будущего", column=col
                    )
                )

    for col in feature_cols:
        meta = meta_by_name.get(col) or {}
        if not meta:
            continue
        if meta["type"] == "id":
            exclude_auto[col] = "ID-подобная колонка исключена автоматически"
        elif meta["nunique"] <= 1:
            exclude_auto[col] = "Константа"
        else:
            1 - meta["missing_pct"] / 100 if False else None
            if meta["type"] != "numeric":
                vc = df[col].value_counts(normalize=True, dropna=True)
                if len(vc) >= 1 and vc.iloc[0] > cfg["constant_share"]:
                    exclude_auto[col] = "Почти константа"

    binary = task_type == "binary"
    y = None
    if binary:
        classes = sorted(target.dropna().unique(), key=str)
        if len(classes) == 2:
            y = (target == classes[1]).astype(float).to_numpy()

    for col in feature_cols:
        meta = meta_by_name.get(col, {})
        if meta.get("type") in ("id", "constant", "text"):
            continue
        if binary and y is not None:
            if meta.get("type") == "numeric":
                auc = _auc_safe(y, pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float))
                if auc is not None and auc > cfg["single_feature_auc_block"]:
                    checks.append(
                        _check(
                            "single_feature_auc",
                            "BLOCK",
                            f"Признак «{col}» почти идеально предсказывает таргет (AUC {auc:.3f}). Похоже на утечку: значение известно только после события",
                            column=col,
                            auc=round(auc, 4),
                        )
                    )
            elif meta.get("type") == "categorical":
                codes = df[col].astype(str)
                if codes.nunique() <= 100:
                    mapped = codes.map({v: i for i, v in enumerate(codes.unique())}).to_numpy(dtype=float)
                    auc = _auc_safe(y, mapped)
                    if auc is not None and auc > cfg["single_feature_auc_block"]:
                        checks.append(
                            _check(
                                "single_feature_auc",
                                "BLOCK",
                                f"Признак «{col}» почти идеально предсказывает таргет (AUC {auc:.3f}) — похоже на утечку",
                                column=col,
                                auc=round(auc, 4),
                            )
                        )
        if meta.get("type") == "numeric" and len(df) > 100:
            x = pd.to_numeric(df[col], errors="coerce")
            t = pd.to_numeric(target, errors="coerce") if task_type == "regression" else None
            if t is not None:
                both = x.notna() & t.notna()
                if both.sum() > 100:
                    corr = float(np.corrcoef(x[both], t[both])[0, 1]) if both.sum() > 1 else 0.0
                    if abs(corr) > cfg["single_feature_corr_block"]:
                        checks.append(
                            _check(
                                "single_feature_corr",
                                "BLOCK",
                                f"Корреляция «{col}» с таргетом {corr:.3f} — почти детерминированная связь, похоже на утечку",
                                column=col,
                                corr=round(corr, 4),
                            )
                        )

    if binary and y is not None:
        for col in feature_cols:
            meta = meta_by_name.get(col, {})
            if not meta or meta["missing_pct"] < 1:
                continue
            indicator = df[col].isna().astype(float).to_numpy()
            pos, neg = y == 1, y == 0
            share_pos, share_neg = indicator[pos].mean(), indicator[neg].mean()
            auc = _auc_safe(y, indicator)
            if auc is not None and auc > cfg["missing_indicator_block"]:
                checks.append(
                    _check(
                        "missing_target_link",
                        "BLOCK",
                        f"Пропуски в «{col}» почти идеально разделяют классы (AUC {auc:.3f}): колонка заполнена только у одного класса",
                        column=col,
                        auc=round(auc, 4),
                    )
                )
            elif auc is not None and auc > cfg["missing_indicator_warn"]:
                checks.append(
                    _check(
                        "missing_target_link",
                        "WARN",
                        f"Пропуски в «{col}» связаны с таргетом (AUC {auc:.3f}) — возможно, сам факт пропуска информативен",
                        column=col,
                        auc=round(auc, 4),
                    )
                )
            elif abs(share_pos - share_neg) > cfg["missing_share_diff_warn"]:
                checks.append(
                    _check(
                        "missing_target_link",
                        "WARN",
                        f"Доля пропусков в «{col}» сильно различается между классами ({share_pos:.0%} против {share_neg:.0%})",
                        column=col,
                    )
                )

    dup = int(df.duplicated(subset=feature_cols + [target_col]).sum())
    if dup > 0:
        checks.append(_check("duplicates", "WARN", f"{dup} полных дубликатов строк — при случайном сплите один объект попадёт и в train, и в test"))

    verdict = "OK"
    if any(c["verdict"] == "WARN" for c in checks):
        verdict = "WARN"
    if any(c["verdict"] == "BLOCK" for c in checks):
        verdict = "BLOCK"
    return {"verdict": verdict, "checks": checks, "exclude_auto": exclude_auto}


def run_split_checks(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    train_idx: np.ndarray,
    holdout_idx: np.ndarray,
    entity_col: str | None,
    split_kind: str = "random",
) -> dict:
    checks: list[dict] = []
    cols = feature_cols + [target_col]

    def row_hashes(idx: object) -> set[int]:
        sub = df.iloc[idx][cols].astype(str)
        return set(map(hash, sub.itertuples(index=False, name=None)))

    if len(holdout_idx) >= 50:
        tr, ho = row_hashes(train_idx), row_hashes(holdout_idx)
        inter = len(tr & ho)
        if inter > 0:
            if split_kind == "out_of_time":
                checks.append(
                    _check(
                        "train_test_overlap",
                        "WARN",
                        f"{inter} строк совпадают в train и holdout — для rolling-срезов это ожидаемо "
                        "(у «спящих» сущностей признаки не меняются между срезами)",
                    )
                )
            else:
                checks.append(_check("train_test_overlap", "BLOCK", f"{inter} строк встречаются и в train, и в holdout — оценка качества будет завышена"))
    if entity_col and entity_col in df.columns:
        tr_ent = set(df.iloc[train_idx][entity_col].astype(str))
        ho_ent = set(df.iloc[holdout_idx][entity_col].astype(str))
        inter = len(tr_ent & ho_ent)
        if inter > 0 and len(holdout_idx) >= 50:
            if split_kind == "out_of_time":
                checks.append(
                    _check(
                        "entity_overlap",
                        "WARN",
                        f"{inter} сущностей «{entity_col}» есть и в train, и в holdout — для rolling-срезов это ожидаемо: "
                        "валидация честна по времени, но модель видит одну сущность в нескольких срезах",
                    )
                )
            else:
                checks.append(
                    _check(
                        "entity_overlap", "BLOCK", f"{inter} сущностей «{entity_col}» попали и в train, и в holdout — нужен сплит по сущностям (group split)"
                    )
                )
    verdict = "OK"
    if any(c["verdict"] == "WARN" for c in checks):
        verdict = "WARN"
    if any(c["verdict"] == "BLOCK" for c in checks):
        verdict = "BLOCK"
    return {"verdict": verdict, "checks": checks}


def run_post_checks(task_type: str, metrics: dict, drivers: list[dict]) -> dict:
    cfg = load_config()
    checks: list[dict] = []
    if task_type in ("binary", "multiclass"):
        auc = metrics.get("roc_auc") or metrics.get("auc")
        if auc is not None and auc > cfg["suspicious_auc"]:
            checks.append(_check("too_good", "WARN", f"ROC-AUC {auc:.3f} подозрительно высок — проверьте признаки на утечку таргета"))
    else:
        r2 = metrics.get("r2")
        if r2 is not None and r2 > cfg["suspicious_r2"]:
            checks.append(_check("too_good", "WARN", f"R² {r2:.3f} подозрительно высок — проверьте признаки на утечку таргета"))
    if drivers:
        total = sum(abs(d["impact"]) for d in drivers) or 1.0
        top = drivers[0]
        share = abs(top["impact"]) / total
        if share > cfg["dominant_feature_block"]:
            checks.append(
                _check(
                    "dominant_feature",
                    "BLOCK",
                    f"Признак «{top['feature']}» даёт {share:.0%} всего влияния — модель, вероятно, выучила утечку",
                    column=top["feature"],
                    share=round(share, 3),
                )
            )
        elif share > cfg["dominant_feature_warn"]:
            checks.append(
                _check(
                    "dominant_feature",
                    "WARN",
                    f"Признак «{top['feature']}» доминирует: {share:.0%} суммарного влияния",
                    column=top["feature"],
                    share=round(share, 3),
                )
            )
    verdict = "OK"
    if any(c["verdict"] == "WARN" for c in checks):
        verdict = "WARN"
    if any(c["verdict"] == "BLOCK" for c in checks):
        verdict = "BLOCK"
    return {"verdict": verdict, "checks": checks}
