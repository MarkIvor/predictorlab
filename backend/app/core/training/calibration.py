import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def fit_calibration(probas: np.ndarray, y: np.ndarray, method: str = "auto") -> dict:
    n = len(y)
    if n < 200:
        return {"kind": "none"}
    kind = "isotonic" if (method == "auto" and n >= 500) or method == "isotonic" else "platt"
    if kind == "isotonic":
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(probas, y)
        return {"kind": "isotonic", "obj": ir}
    lr = LogisticRegression(C=1e3, max_iter=1000)
    lr.fit(probas.reshape(-1, 1), y)
    return {"kind": "platt", "obj": lr}


def apply_calibration(calibrator: dict, probas: np.ndarray) -> np.ndarray:
    if not calibrator or calibrator.get("kind") == "none":
        return probas
    if calibrator["kind"] == "isotonic":
        return np.asarray(calibrator["obj"].predict(probas))
    return np.asarray(calibrator["obj"].predict_proba(probas.reshape(-1, 1))[:, 1])


def brier_score(probas: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((probas - y) ** 2))


def reliability_curve(probas: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for i in range(bins):
        mask = (probas >= edges[i]) & (probas < edges[i + 1]) if i < bins - 1 else (probas >= edges[i]) & (probas <= edges[i + 1])
        if mask.sum() == 0:
            continue
        out.append(
            {
                "bin": round(float(edges[i]), 2),
                "predicted": float(probas[mask].mean()),
                "actual": float(y[mask].mean()),
                "count": int(mask.sum()),
            }
        )
    return out
