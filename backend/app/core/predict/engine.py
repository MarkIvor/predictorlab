import uuid
from typing import Any

import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.registry import artifacts
from app.core.training import candidates as cand
from app.core.training import preprocess as prep
from app.core.training.calibration import apply_calibration
from app.core.uncertainty import conformal as conf
from app.core.uncertainty import ood as ood_mod

_cache: dict[int, dict] = {}


class ValidationError(Exception):
    pass


def new_prediction_id() -> str:
    return f"prd_{uuid.uuid4().hex[:16]}"


def load_bundle(version_id: int, dir_rel: str) -> dict:
    if version_id in _cache:
        return _cache[version_id]
    settings = get_settings()
    vdir = settings.storage_path / dir_rel
    ok, reason = artifacts.verify_version(vdir)
    if not ok:
        raise PermissionError(f"Артефакты не прошли проверку: {reason}")
    pipeline = artifacts.load_joblib(vdir / "pipeline.joblib")
    conformal = artifacts.load_joblib(vdir / "conformal.joblib")
    ood = artifacts.load_joblib(vdir / "ood.joblib")
    schema = artifacts.load_json(vdir / "schema.json")
    metrics_path = vdir / "metrics.json"
    metrics = artifacts.load_json(metrics_path) if metrics_path.exists() else {}
    bg_path = vdir / "shap_background.parquet"
    bg = pd.read_parquet(bg_path) if bg_path.exists() else None
    bundle = {
        "pipeline": pipeline,
        "conformal": conformal,
        "ood": ood,
        "schema": schema,
        "metrics": metrics,
        "background": bg,
        "dir": str(vdir),
        "explainer": None,
    }
    if len(_cache) > 20:
        _cache.clear()
    _cache[version_id] = bundle
    return bundle


def invalidate_cache() -> None:
    _cache.clear()


def validate_record(record: dict, schema: dict) -> tuple[dict, list[str]]:
    props = schema["input_schema"]["properties"]
    clean: dict = {}
    warnings: list[str] = []
    known = set(props)
    for k, v in (record or {}).items():
        if k not in known:
            warnings.append(f"Поле «{k}» не используется моделью и проигнорировано")
            continue
        p = props[k]
        if v is None or (isinstance(v, str) and v.strip() == ""):
            clean[k] = None
            continue
        try:
            if p["type"] == "number":
                clean[k] = float(v)
            elif p["type"] == "boolean":
                if isinstance(v, str):
                    low = v.strip().lower()
                    if low in ("true", "yes", "1", "да", "y", "t", "истина"):
                        clean[k] = True
                    elif low in ("false", "no", "0", "нет", "n", "f", "ложь"):
                        clean[k] = False
                    else:
                        raise ValueError(v)
                else:
                    clean[k] = bool(v)
            elif p["type"] == "string" and p.get("format") == "date-time":
                parsed = pd.to_datetime(v, errors="coerce")
                if pd.isna(parsed):
                    raise ValueError(v)
                clean[k] = str(parsed)
            else:
                clean[k] = str(v)
        except (ValueError, TypeError):
            raise ValidationError(f"Поле «{k}»: ожидается {p['type']}, получено «{v}»") from None
    return clean, warnings


def _cat_idx(X: pd.DataFrame, spec: dict) -> list[int]:
    return [X.columns.get_loc(c) for c in spec.get("categorical", []) if c in X.columns]


def predict_matrix(bundle: dict, df_raw: pd.DataFrame) -> np.ndarray:
    pipeline = bundle["pipeline"]
    spec = pipeline["spec"]
    task = pipeline["task_type"]
    kind = pipeline["kind"]
    est = pipeline["estimator"]
    X = prep.transform(df_raw, spec)
    if task == "regression":
        if kind == "ensemble":
            return np.asarray(est.predict(X)).ravel()
        if kind == "catboost":
            return np.asarray(est.predict(X)).ravel()
        if kind == "lightgbm":
            return np.asarray(est.predict(cand.lgbm_view(X, spec))).ravel()
        return np.asarray(est.predict(X)).ravel()
    if kind == "ensemble":
        return np.atleast_2d(est.predict_proba(X))
    if kind == "catboost":
        return np.atleast_2d(est.predict_proba(X))
    if kind == "lightgbm":
        return np.atleast_2d(est.predict_proba(cand.lgbm_view(X, spec)))
    return np.atleast_2d(est.predict_proba(X))


def _num_matrix(bundle: dict, df_raw: pd.DataFrame) -> pd.DataFrame:
    spec = bundle["pipeline"]["spec"]
    X = prep.transform(df_raw, spec)
    num_cols = [c for c in spec["feature_cols"] if c not in spec.get("categorical", [])]
    return X[num_cols]


def _ood_flags(bundle: dict, df_raw: pd.DataFrame) -> list[bool]:
    try:
        X_num = _num_matrix(bundle, df_raw)
        return [bool(v < bundle["ood"]["threshold"]) for v in ood_mod.ood_scores(bundle["ood"], X_num.to_numpy(dtype=float))]
    except Exception:
        return [False] * len(df_raw)


def _get_explainer(bundle: dict) -> Any:
    if bundle["explainer"] is None:
        import shap

        pipeline = bundle["pipeline"]
        est = pipeline["estimator"]
        if pipeline["kind"] == "ensemble":
            est = est.models[0]
        bundle["explainer"] = shap.TreeExplainer(est)
    return bundle["explainer"]


def _reasons(bundle: dict, df_raw: pd.DataFrame, row_i: int, top: int = 5) -> list[dict]:
    pipeline = bundle["pipeline"]
    spec = pipeline["spec"]
    kind = pipeline["kind"]
    X = prep.transform(df_raw, spec)
    row = X.iloc[[row_i]]
    if kind == "linear":
        from app.core.explain.shap_explainer import _linear_shap

        sh = _linear_shap(pipeline, bundle["background"], row).ravel()
    else:
        explainer = _get_explainer(bundle)
        sh = explainer.shap_values(row)
        if isinstance(sh, list):
            sh = sh[-1]
        sh = np.asarray(sh)
        if sh.ndim == 3:
            sh = sh[0, :, -1]
        sh = sh.ravel()
    from app.core.explain.shap_explainer import local_reasons

    values = {c: df_raw.iloc[row_i].get(c) for c in df_raw.columns}
    return local_reasons(sh, spec["feature_cols"], values, top=top)


def _reason_text(feature: str, value: Any, impact: float, task: str, classes: list | None) -> str:
    val_str = value
    if isinstance(value, float):
        val_str = round(value, 2)
    src = feature.split("__")[0]
    if task == "binary" and classes and len(classes) == 2:
        direction = "повышает" if impact >= 0 else "снижает"
        return f"{src} = {val_str}: {direction} вероятность «{classes[1]}» на {abs(impact) * 100:.0f} п.п."
    sign = "+" if impact >= 0 else "−"
    return f"{src} = {val_str}: {sign}{abs(impact):.2f} к прогнозу"


def predict_records(bundle: dict, records: list[dict], threshold: float | None = None, include_reasons: bool = False) -> tuple[list[dict], list[str]]:
    task = bundle["pipeline"]["task_type"]
    classes = bundle["pipeline"].get("classes")
    calibrator = bundle["pipeline"].get("calibrator")
    conformal = bundle["conformal"]
    schema = bundle["schema"]

    validated = []
    all_warnings: list[str] = []
    for r in records:
        clean, warns = validate_record(r, schema)
        validated.append(clean)
        all_warnings.extend(warns[:3])
    df_raw = pd.DataFrame(validated, columns=list(schema["input_schema"]["properties"].keys()))
    matrix = predict_matrix(bundle, df_raw)
    ood_flags = _ood_flags(bundle, df_raw)

    thr = threshold if threshold is not None else 0.5
    results = []
    for i in range(len(records)):
        pid = new_prediction_id()
        ood = bool(ood_flags[i])
        out = {"prediction_id": pid, "out_of_distribution": ood}
        if ood:
            out["ood_note"] = "Объект сильно отличается от обучающей выборки — прогноз может быть ненадёжным"
        if task == "regression":
            pred = float(matrix[i])
            lo, hi = conf.regression_interval(pred, conformal)
            out.update(
                {
                    "prediction": round(pred, 4),
                    "interval_low": round(lo, 4),
                    "interval_high": round(hi, 4),
                    "conformal": {"coverage": conformal.get("alpha", 0.9)},
                }
            )
        elif task == "binary":
            p_raw = float(matrix[i][1])
            p = float(apply_calibration(calibrator, np.array([p_raw]))[0]) if calibrator else p_raw
            pred_set = conf.predict_set(np.array([1 - p_raw, p_raw]), conformal, classes)
            label = classes[1] if p >= thr else classes[0]
            out.update(
                {
                    "label": str(label),
                    "probability": round(p, 4),
                    "decision": bool(p >= thr),
                    "threshold": thr,
                    "conformal": {
                        "coverage": conformal.get("alpha", 0.9),
                        "prediction_set": [str(c) for c in pred_set],
                    },
                }
            )
            if len(pred_set) != 1:
                out["confidence_note"] = "Модель неуверенно разделяет классы — смотрите множество прогноза"
        else:
            proba = matrix[i]
            k = len(proba)
            pred_set = conf.predict_set(proba, conformal, list(range(k)))
            best = int(np.argmax(proba))
            out.update(
                {
                    "label": str(classes[best]) if classes else str(best),
                    "probability": round(float(proba[best]), 4),
                    "conformal": {
                        "coverage": conformal.get("alpha", 0.9),
                        "prediction_set": [str(classes[int(c)]) if classes else str(c) for c in pred_set],
                    },
                }
            )
        if include_reasons:
            reasons = _reasons(bundle, df_raw, i)
            for r in reasons:
                r["text"] = _reason_text(r["feature"], r["value"], r["impact"], task, classes)
            out["top_reasons"] = reasons
        results.append(out)
    from app.services.jsonsafe import json_safe

    return json_safe(results), all_warnings
