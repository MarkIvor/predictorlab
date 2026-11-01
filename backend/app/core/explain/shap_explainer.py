import numpy as np
import pandas as pd


def make_background(X: pd.DataFrame, y: np.ndarray | None, max_rows: int = 500, seed: int = 42) -> pd.DataFrame:
    if len(X) <= max_rows:
        return X.copy()
    rng = np.random.RandomState(seed)
    if y is not None and len(np.unique(y[~np.isnan(y)])) == 2:
        pos_idx = np.where(y == 1)[0]
        neg_idx = np.where(y == 0)[0]
        n_half = max_rows // 2
        take_pos = rng.choice(pos_idx, min(len(pos_idx), max(1, n_half)), replace=False)
        take_neg = rng.choice(neg_idx, min(len(neg_idx), max(1, max_rows - len(take_pos))), replace=False)
        take = np.concatenate([take_pos, take_neg])
    else:
        take = rng.choice(len(X), max_rows, replace=False)
    return X.iloc[take].copy()


def shap_matrix(pipeline: dict, X_bg: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
    import shap
    kind = pipeline["kind"]
    est = pipeline["estimator"]
    if kind == "linear":
        return _linear_shap(pipeline, X_bg, X)
    model = est
    if kind == "ensemble":
        model = est.models[0]
    explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(X)
    if isinstance(values, list):
        values = values[-1]
    values = np.asarray(values)
    if values.ndim == 3:
        values = values[:, :, -1]
    return values


def _linear_shap(pipeline: dict, X_bg: pd.DataFrame, X: pd.DataFrame) -> np.ndarray:
    est = pipeline["estimator"]
    pre = est.named_steps.get("pre")
    est_lin = est.named_steps.get("est")
    spec = pipeline.get("spec") or {}
    feature_cols = spec.get("feature_cols") or list(X.columns)
    n = len(X)
    if pre is None or est_lin is None or not hasattr(est_lin, "coef_"):
        return np.zeros((n, len(feature_cols)))
    Xt = np.asarray(pre.transform(X), dtype=float)
    Xt_bg = np.asarray(pre.transform(X_bg), dtype=float)
    coef = est_lin.coef_
    if coef.ndim > 1:
        coef = coef[-1]
    contrib = (Xt - np.nanmean(Xt_bg, axis=0)) * coef[: Xt.shape[1]]
    out = np.zeros((n, len(feature_cols)))
    try:
        names = pre.get_feature_names_out()
    except Exception:
        return contrib
    if len(names) != contrib.shape[1]:
        return contrib
    col_index = {col: i for i, col in enumerate(feature_cols)}
    for j, name in enumerate(names):
        body = name.split("__", 1)[-1]
        matched = None
        for col in sorted(feature_cols, key=len, reverse=True):
            if body == col or body.startswith(col + "_"):
                matched = col
                break
        if matched is None and body in col_index:
            matched = body
        if matched is not None:
            out[:, col_index[matched]] += contrib[:, j]
    return out


def global_drivers(shap_values: np.ndarray, feature_cols: list[str]) -> list[dict]:
    mean_abs = np.mean(np.abs(shap_values), axis=0)
    mean_signed = np.mean(shap_values, axis=0)
    order = np.argsort(-mean_abs)
    return [
        {
            "feature": feature_cols[i],
            "impact": float(mean_abs[i]),
            "direction": "up" if mean_signed[i] >= 0 else "down",
        }
        for i in order
    ]


def dependence_data(X: pd.DataFrame, shap_values: np.ndarray, feature: str, max_points: int = 300, seed: int = 1) -> dict:
    if feature not in X.columns:
        return {"feature": feature, "x": [], "y": []}
    x = X[feature].to_numpy(dtype=float, errors="ignore")
    y = shap_values[:, list(X.columns).index(feature)]
    mask = ~pd.isna(x)
    x, y = x[mask], y[mask]
    if len(x) > max_points:
        idx = np.random.RandomState(seed).choice(len(x), max_points, replace=False)
        x, y = x[idx], y[idx]
    order = np.argsort(x)
    return {"feature": feature, "x": [float(v) for v in x[order]], "y": [float(v) for v in y[order]]}


def local_reasons(shap_row: np.ndarray, feature_cols: list[str], values_row: dict, top: int = 5) -> list[dict]:
    shap_row = np.asarray(shap_row).ravel()
    order = np.argsort(-np.abs(shap_row))[:top]
    reasons = []
    for i in order:
        feature = feature_cols[i]
        val = values_row.get(feature)
        impact = float(shap_row[i])
        reasons.append({
            "feature": feature,
            "value": None if val is None or (isinstance(val, float) and np.isnan(val)) else val,
            "impact": round(impact, 6),
            "direction": "up" if impact >= 0 else "down",
        })
    return reasons
