import time
from typing import Any

import numpy as np

from app.core.predict import engine


def predict_proba_one(bundle: dict, record: dict, threshold: float | None = None) -> dict:
    results, _ = engine.predict_records(bundle, [record], threshold=threshold, include_reasons=False)
    return results[0]


def _candidate_values(feature: str, cfg: dict, current: Any) -> list:
    if "allowed_values" in cfg:
        return [v for v in cfg["allowed_values"] if v != current]
    lo, hi = float(cfg.get("min", current)), float(cfg.get("max", current))
    direction = cfg.get("direction", "both")
    values: list[Any] = []
    if direction in ("both", "down") and current is not None and lo < float(current):
        values.extend(np.linspace(float(current), lo, 6)[1:])
    if direction in ("both", "up") and current is not None and hi > float(current):
        values.extend(np.linspace(float(current), hi, 6)[1:])
    return values


def _change_cost(feature: str, cfg: dict, old: Any, new: Any) -> float:
    if "allowed_values" in cfg:
        return float(cfg.get("cost_flat", 0))
    cost_per_unit = float(cfg.get("cost_per_unit", 0))
    try:
        return abs(float(new) - float(old)) * cost_per_unit
    except (TypeError, ValueError):
        return 0.0


def find_counterfactual(
    bundle: dict, record: dict, actionable: dict, threshold: float, direction: str = "below", timeout: float = 10.0, cost_matrix: dict | None = None
) -> dict | None:
    start = time.monotonic()
    base = predict_proba_one(bundle, record, threshold)
    p0 = base.get("probability")
    if p0 is None:
        return None
    task = bundle["pipeline"]["task_type"]
    if task != "binary":
        return None
    if direction == "below" and p0 < threshold:
        return {"changes": {}, "cost_rub": 0.0, "probability_before": p0, "probability_after": p0, "already_ok": True, "expected_roi_rub": 0.0}
    if direction == "above" and p0 >= threshold:
        return {"changes": {}, "cost_rub": 0.0, "probability_before": p0, "probability_after": p0, "already_ok": True, "expected_roi_rub": 0.0}

    features = [f for f, cfg in (actionable or {}).items() if f in bundle["schema"]["input_schema"]["properties"]]
    rnd = np.random.RandomState(42)
    best_result = None
    deadline = start + max(1.0, timeout)

    for restart in range(12):
        if time.monotonic() > deadline:
            break
        order = list(features) if restart == 0 else rnd.permutation(features).tolist()
        current = dict(record)
        changes: dict = {}
        total_cost = 0.0
        p_cur = p0
        for feature in order:
            if time.monotonic() > deadline:
                break
            cfg = actionable[feature]
            cur_val = current.get(feature)
            candidates = _candidate_values(feature, cfg, cur_val)
            if not candidates:
                continue
            rows: list[Any] = []
            kept = []
            for v in candidates:
                trial = dict(current)
                trial[feature] = v
                try:
                    out = predict_proba_one(bundle, trial, threshold)
                except engine.ValidationError:
                    continue
                p = out.get("probability")
                if p is None:
                    continue
                rows.append((v, p))
                kept.append(v)
            if not rows:
                continue
            flipped = [(v, p) for v, p in rows if (p < threshold if direction == "below" else p >= threshold)]
            if flipped:
                v, p = flipped[0]
                cost = _change_cost(feature, cfg, cur_val, v)
                current[feature] = v
                changes[feature] = v
                total_cost += cost
                p_cur = p
                break
            if direction == "below":
                v, p = min(rows, key=lambda r: r[1])
            else:
                v, p = max(rows, key=lambda r: r[1])
            improvement = abs(p - p_cur)
            cost = _change_cost(feature, cfg, cur_val, v)
            if improvement > 0.001 and cost < 1e12:
                current[feature] = v
                changes[feature] = v
                total_cost += cost
                p_cur = p
        success = (p_cur < threshold) if direction == "below" else (p_cur >= threshold)
        if success and (best_result is None or total_cost < best_result["cost_rub"]):
            best_result = {"changes": changes, "cost_rub": round(total_cost, 2), "probability_before": round(p0, 4), "probability_after": round(p_cur, 4)}
    if best_result is None:
        return None

    roi = None
    if cost_matrix and direction in ("below", "above"):
        benefit = float(cost_matrix.get("benefit_tp", 0) or 0)
        delta = (
            (best_result["probability_before"] - best_result["probability_after"])
            if direction == "below"
            else (best_result["probability_after"] - best_result["probability_before"])
        )
        roi = round(benefit * delta - best_result["cost_rub"], 2)
    best_result["expected_roi_rub"] = roi
    best_result["already_ok"] = False
    return best_result
