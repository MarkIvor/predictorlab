import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer


def fit_ood(X_num: np.ndarray, contamination: float = 0.01, max_rows: int = 20_000, seed: int = 42) -> dict:
    if len(X_num) > max_rows:
        idx = np.random.RandomState(seed).choice(len(X_num), max_rows, replace=False)
        X_num = X_num[idx]
    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X_num)
    forest = IsolationForest(n_estimators=100, contamination=contamination, random_state=seed, n_jobs=-1)
    forest.fit(X_imp)
    scores = forest.score_samples(X_imp)
    threshold = float(np.quantile(scores, contamination * 100))
    return {"imputer": imputer, "forest": forest, "threshold": threshold, "contamination": contamination}


def ood_scores(ood: dict, X_num: np.ndarray) -> np.ndarray:
    X_imp = ood["imputer"].transform(X_num)
    return np.asarray(ood["forest"].score_samples(X_imp))


def is_ood(ood: dict, X_num_row: np.ndarray) -> bool:
    if not ood:
        return False
    score = ood_scores(ood, X_num_row.reshape(1, -1))[0]
    return bool(score < ood["threshold"])
