import numpy as np
import pandas as pd


def psi_numeric(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float | None:
    ref = pd.Series(reference).dropna()
    cur = pd.Series(current).dropna()
    if len(ref) < 30 or len(cur) < 30:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return None
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts = np.histogram(ref, bins=edges)[0] / len(ref)
    cur_counts = np.histogram(cur, bins=edges)[0] / len(cur)
    return _psi_from_counts(ref_counts, cur_counts)


def psi_categorical(reference: pd.Series, current: pd.Series, top: int = 20) -> float | None:
    ref = reference.dropna().astype(str)
    cur = current.dropna().astype(str)
    if len(ref) < 30 or len(cur) < 30:
        return None
    top_vals = ref.value_counts().head(top).index.tolist()
    ref_counts = ref.isin(top_vals).mean()
    cur_counts = cur.isin(top_vals).mean()
    return _psi_from_counts(
        np.array([ref_counts, 1 - ref_counts]),
        np.array([cur_counts, 1 - cur_counts]),
    )


def _psi_from_counts(ref_counts: np.ndarray, cur_counts: np.ndarray) -> float:
    eps = 1e-6
    ref_counts = np.clip(ref_counts, eps, None)
    cur_counts = np.clip(cur_counts, eps, None)
    return float(np.sum((cur_counts - ref_counts) * np.log(cur_counts / ref_counts)))


def psi_frame(reference: pd.DataFrame, current: pd.DataFrame, categorical: list[str]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for col in reference.columns:
        if col not in current.columns:
            continue
        if col in categorical:
            out[col] = psi_categorical(reference[col], current[col])
        else:
            try:
                out[col] = psi_numeric(
                    pd.to_numeric(reference[col], errors="coerce").to_numpy(),
                    pd.to_numeric(current[col], errors="coerce").to_numpy())
            except (TypeError, ValueError):
                out[col] = None
    return out


def status_from_psi(psi: float | None, warn: float, drift: float) -> str:
    if psi is None:
        return "OK"
    if psi > drift:
        return "DRIFT"
    if psi > warn:
        return "WARN"
    return "OK"
