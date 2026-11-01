from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def _num_cat(spec: dict) -> tuple[list[str], list[str]]:
    num = [c for c in spec["feature_cols"] if not _is_cat(spec, c)]
    cat = [c for c in spec["categorical"]]
    return num, cat


def _is_cat(spec: dict, col: str) -> bool:
    return col in spec.get("categorical", [])


def fit_cat_levels(X: pd.DataFrame, spec: dict) -> dict:
    levels = {}
    for col in spec.get("categorical", []):
        if col in X.columns:
            levels[col] = [str(v) for v in X[col].dropna().unique()]
    spec["cat_levels"] = levels
    return levels


def build_catboost(task_type: str, spec: dict, params: dict | None = None) -> object:
    p = dict(params or {})
    p.setdefault("iterations", 500)
    p.setdefault("depth", 6)
    p.setdefault("learning_rate", 0.1)
    p.setdefault("random_seed", 42)
    p.setdefault("verbose", False)
    p.setdefault("thread_count", -1)
    if task_type == "regression":
        p.setdefault("loss_function", "RMSE")
        return CatBoostRegressor(**p)
    if task_type == "multiclass":
        return CatBoostClassifier(**p)
    return CatBoostClassifier(**p)


def build_lightgbm(task_type: str, spec: dict, params: dict | None = None) -> object:
    p = dict(params or {})
    p.setdefault("n_estimators", 400)
    p.setdefault("learning_rate", 0.05)
    p.setdefault("num_leaves", 63)
    p.setdefault("random_state", 42)
    p.setdefault("verbose", -1)
    p.setdefault("n_jobs", -1)
    if task_type == "regression":
        return LGBMRegressor(**p)
    return LGBMClassifier(**p)


def build_linear(task_type: str, spec: dict) -> Pipeline:
    num, cat = _num_cat(spec)
    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore", min_frequency=0.01))]), cat),
        ]
    )
    estimator = Ridge(alpha=1.0) if task_type == "regression" else LogisticRegression(max_iter=2000, C=1.0)
    return Pipeline([("pre", preprocessor), ("est", estimator)])


class EnsembleModel:
    def __init__(self, models: list, weights: list[float], task_type: str, kinds: list[str] | None = None, cat_levels: dict | None = None):
        self.models = models
        self.weights = weights
        self.task_type = task_type
        self.kinds = kinds or ["catboost"] * len(models)
        self.cat_levels = cat_levels or {}

    def _views(self, X: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        X_str = X
        X_cat = X.copy()
        for col, cats in self.cat_levels.items():
            if col in X_cat.columns:
                X_cat[col] = pd_categorical(X_cat[col].astype(str), categories=cats)
        return X_str, X_cat

    def _member_proba(self, m: Any, kind: str, X_str: pd.DataFrame, X_cat: pd.DataFrame) -> np.ndarray:
        if kind == "catboost":
            p = m.predict_proba(X_str)
        elif kind == "lightgbm":
            p = m.predict_proba(X_cat)
        else:
            p = m.predict_proba(X_str)
        return np.atleast_2d(p)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X_str, X_cat = self._views(X)
        probas: np.ndarray | None = None
        for w, m, k in zip(self.weights, self.models, self.kinds, strict=False):
            p = self._member_proba(m, k, X_str, X_cat)
            probas = w * p if probas is None else probas + w * p
        assert probas is not None
        return probas

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.task_type == "regression":
            X_str, X_cat = self._views(X)
            out: np.ndarray | None = None
            for w, m, k in zip(self.weights, self.models, self.kinds, strict=False):
                if k == "catboost":
                    p = m.predict(X_str)
                elif k == "lightgbm":
                    p = m.predict(X_cat)
                else:
                    p = m.predict(X_str)
                out = w * np.asarray(p).ravel() if out is None else out + w * np.asarray(p).ravel()
            assert out is not None
            return out
        proba = self.predict_proba(X)
        return np.argmax(proba, axis=1)


def fit_catboost_matrix(est: Any, X: pd.DataFrame, y: Any, spec: dict, sample_weight: Any = None) -> Any:
    cat_idx = [X.columns.get_loc(c) for c in spec.get("categorical", []) if c in X.columns]
    kwargs = {}
    if cat_idx:
        kwargs["cat_features"] = cat_idx
    if sample_weight is not None:
        kwargs["sample_weight"] = sample_weight
    est.fit(X, y, **kwargs)
    return est


def catboost_predict_proba(est: Any, X: pd.DataFrame, spec: dict) -> np.ndarray:
    cat_idx = [X.columns.get_loc(c) for c in spec.get("categorical", []) if c in X.columns]
    proba = est.predict_proba(X, cat_features=cat_idx) if cat_idx else est.predict_proba(X)
    return np.atleast_2d(proba)


def lgbm_view(X: pd.DataFrame, spec: dict) -> pd.DataFrame:
    X = X.copy()
    levels = spec.get("cat_levels", {})
    for col, cats in levels.items():
        if col in X.columns:
            X[col] = pd_categorical(X[col].astype(str), categories=cats)
    return X


def apply_cat_levels(X: pd.DataFrame, spec: dict) -> pd.DataFrame:
    return lgbm_view(X, spec)


def pd_categorical(series: pd.Series, categories: list) -> Any:
    import pandas as pd

    return pd.Categorical(series, categories=categories)
