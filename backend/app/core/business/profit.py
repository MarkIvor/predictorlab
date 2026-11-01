import numpy as np
import pandas as pd


def _counts_at(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> tuple[int, int, int]:
    treated = proba >= threshold
    tp = int(np.sum(treated & (y_true == 1)))
    fp = int(np.sum(treated & (y_true == 0)))
    fn = int(np.sum(~treated & (y_true == 1)))
    return tp, fp, fn


def profit_at(tp: int, fp: int, fn: int, cost: dict) -> float:
    benefit = float(cost.get("benefit_tp", 0))
    action = float(cost.get("action_cost", 0))
    fn_cost = float(cost.get("fn_cost", 0))
    return tp * (benefit - action) - fp * action - fn * fn_cost


def compute_threshold(holdout_frame: pd.DataFrame, cost: dict) -> dict:
    y_true = holdout_frame["y_true"].to_numpy(dtype=int)
    proba = holdout_frame["proba"].to_numpy(dtype=float)
    n_pos = float(np.sum(y_true == 1))
    n_neg = float(np.sum(y_true == 0))
    base_rate = n_pos / max(len(y_true), 1)

    capacity = cost.get("capacity")
    thresholds = np.unique(proba)
    thresholds = np.sort(thresholds)[::-1]
    if capacity:
        thresholds = thresholds[: int(capacity)]
    if len(thresholds) == 0:
        thresholds = np.array([0.5])

    curve = []
    best = None
    for t in thresholds:
        tp, fp, fn = _counts_at(y_true, proba, float(t))
        profit = profit_at(tp, fp, fn, cost)
        point = {"threshold": round(float(t), 6), "tp": tp, "fp": fp, "fn": fn, "profit": round(profit, 2)}
        curve.append(point)
        if best is None or profit > best["profit"]:
            best = point

    if not best:
        best = {"threshold": 0.5, "tp": 0, "fp": 0, "fn": 0, "profit": 0.0}
    threshold = best["threshold"]
    n_treated = best["tp"] + best["fp"]

    tp_all, fp_all, fn_all = _counts_at(y_true, proba, 0.0)
    profit_all = profit_at(tp_all, fp_all, fn_all, cost)

    exp_tp = n_treated * base_rate
    exp_fp = n_treated * (1 - base_rate)
    profit_random = profit_at(int(round(exp_tp)), int(round(exp_fp)), int(n_pos - exp_tp), cost)

    scale = float(cost.get("scale", 1) or 1)
    period_label = cost.get("period_label", "holdout-период")

    step = max(1, len(curve) // 200)
    sampled_curve = curve[::step]
    if sampled_curve[-1] is not curve[-1]:
        sampled_curve.append(curve[-1])

    return {
        "threshold": threshold,
        "profit": best["profit"],
        "profit_scaled": round(best["profit"] * scale, 2),
        "profit_random": round(profit_random, 2),
        "profit_random_scaled": round(profit_random * scale, 2),
        "profit_all": round(profit_all, 2),
        "profit_all_scaled": round(profit_all * scale, 2),
        "vs_random": round(best["profit"] - profit_random, 2),
        "vs_all": round(best["profit"] - profit_all, 2),
        "curve": sampled_curve,
        "n_treated": int(n_treated),
        "tp": best["tp"], "fp": best["fp"], "fn": best["fn"],
        "base_rate": round(base_rate, 4),
        "capacity": capacity,
        "scale": scale,
        "period_label": period_label,
        "assumptions": {
            "benefit_tp": cost.get("benefit_tp", 0),
            "action_cost": cost.get("action_cost", 0),
            "fn_cost": cost.get("fn_cost", 0),
            "n_holdout": int(len(y_true)),
        },
        "formulas": [
            "Прибыль(порог) = TP × (выгода_TP − стоимость_действия) − FP × стоимость_действия − FN × потери_пропуска",
            "TP/FP/FN считаются на holdout при выбранном пороге вероятности",
            "«Наугад» = выбираем столько же объектов случайно: ожидаемые TP = N_обработанных × базовая_доля_класса",
            "«Обрабатывать всех» = порог 0: TP = всем положительным, FP = всем отрицательным",
            f"Масштаб ×{scale} применён к значениям за период: {period_label}",
        ],
    }


def regression_cost(holdout_frame: pd.DataFrame, cost: dict) -> dict:
    y = holdout_frame["y_true"].to_numpy(dtype=float)
    pred = holdout_frame["pred"].to_numpy(dtype=float)
    cost_over = float(cost.get("cost_over", 1))
    cost_under = float(cost.get("cost_under", 1))
    over = np.maximum(pred - y, 0)
    under = np.maximum(y - pred, 0)
    total = float(np.sum(cost_over * over + cost_under * under))
    med = float(np.median(y))
    base_over = np.maximum(med - y, 0)
    base_under = np.maximum(y - med, 0)
    baseline_total = float(np.sum(cost_over * base_over + cost_under * base_under))
    scale = float(cost.get("scale", 1) or 1)
    return {
        "cost_total": round(total * scale, 2),
        "cost_baseline": round(baseline_total * scale, 2),
        "saving": round((baseline_total - total) * scale, 2),
        "cost_over": cost_over,
        "cost_under": cost_under,
        "scale": scale,
        "n": int(len(y)),
        "formulas": [
            "Стоимость = Σ (стоимость_перепрогноза × max(ŷ − y, 0) + стоимость_недопрогноза × max(y − ŷ, 0))",
            "Baseline — предсказывать медиану holdout",
        ],
    }
