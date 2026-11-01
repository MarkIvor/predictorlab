import math

import numpy as np


def calibrate_regression(pred_cal: np.ndarray, y_cal: np.ndarray, alpha: float = 0.9) -> dict:
    residuals = np.abs(np.asarray(pred_cal) - np.asarray(y_cal))
    n = len(residuals)
    if n == 0:
        return {"alpha": alpha, "q": 0.0, "method": "abs_residual", "n_calib": 0}
    q_level = min(1.0, math.ceil((n + 1) * alpha) / n)
    q = float(np.quantile(residuals, q_level))
    return {"alpha": alpha, "q": q, "method": "abs_residual", "n_calib": n}


def regression_interval(pred: float, conformal: dict) -> tuple[float, float]:
    q = conformal.get("q", 0.0)
    return float(pred - q), float(pred + q)


def _aps_scores(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    scores = np.empty(len(probs))
    for i in range(len(probs)):
        order = np.argsort(-probs[i])
        cum = np.cumsum(probs[i][order])
        rank = int(np.where(order == int(y[i]))[0][0])
        scores[i] = 1.0 - cum[rank]
    return scores


def calibrate_classification(probs_cal: np.ndarray, y_cal: np.ndarray, alpha: float = 0.9) -> dict:
    """Adaptive Prediction Sets (Romano et al.): маргинальное покрытие ≥ α."""
    n, k = probs_cal.shape
    if n == 0:
        return {"alpha": alpha, "q": 1.0 - alpha, "method": "aps", "n_calib": 0, "k": k}
    scores = _aps_scores(probs_cal, y_cal)
    q_level = min(1.0, math.ceil((n + 1) * alpha) / n)
    q = float(np.quantile(scores, q_level))
    return {"alpha": alpha, "q": q, "method": "aps", "n_calib": n, "k": k}


def predict_set(probs_row: np.ndarray, conformal: dict, classes: list) -> list:
    q = conformal.get("q", 1.0 - conformal.get("alpha", 0.9))
    needed = max(0.0, 1.0 - q)
    order = np.argsort(-probs_row)
    cum = np.cumsum(probs_row[order])
    out = []
    for rank, cls_idx in enumerate(order):
        out.append(classes[int(cls_idx)])
        if cum[rank] >= needed:
            break
    return out


def classification_confidence(probs_row: np.ndarray) -> float:
    return float(np.max(probs_row))
