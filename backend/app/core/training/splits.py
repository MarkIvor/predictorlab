from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SplitPlan:
    kind: str
    train_idx: list[int]
    holdout_idx: list[int]
    cv: list[tuple[list[int], list[int]]] = field(default_factory=list)
    calib_idx: list[int] = field(default_factory=list)
    baseline: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "baseline": self.baseline,
            "info": self.info,
            "n_train": len(self.train_idx),
            "n_holdout": len(self.holdout_idx),
            "n_calib": len(self.calib_idx),
            "cv_folds": len(self.cv),
        }


def _positions(index: np.ndarray) -> list[int]:
    return [int(i) for i in index]


def make_splits(df: pd.DataFrame, target_col: str, task_type: str,
                event_time_col: str | None, entity_col: str | None,
                holdout_frac: float = 0.2, seed: int = 42) -> SplitPlan:
    n = len(df)
    rng = np.random.RandomState(seed)
    positions = np.arange(n)

    target = df[target_col]

    if task_type == "timeseries":
        return _time_splits(df, target_col, event_time_col, holdout_frac)

    if event_time_col and event_time_col in df.columns:
        dt = pd.to_datetime(df[event_time_col], errors="coerce")
        order = np.argsort(dt.to_numpy(), kind="stable")
        n_hold = max(1, int(n * holdout_frac))
        holdout_idx = order[-n_hold:]
        train_idx = order[:-n_hold]
        plan = SplitPlan(kind="out_of_time", train_idx=_positions(train_idx), holdout_idx=_positions(holdout_idx))
        n_train = len(train_idx)
        n_calib = max(1, int(n_train * 0.1))
        plan.calib_idx = _positions(train_idx[-n_calib:])
        core = train_idx[:-n_calib]
        plan.cv = _expanding_window(core)
        plan.info = {
            "event_time_col": event_time_col,
            "holdout_period": [str(dt.iloc[holdout_idx].min()), str(dt.iloc[holdout_idx].max())],
            "train_period": [str(dt.iloc[train_idx].min()), str(dt.iloc[train_idx].max())],
        }
        plan.baseline = _baseline(target.iloc[train_idx], task_type)
        return plan

    shuffled = rng.permutation(n)
    n_hold = max(1, int(n * holdout_frac))
    if task_type in ("binary", "multiclass"):
        hold_mask = np.zeros(n, dtype=bool)
        for cls in target.dropna().unique():
            cls_pos = positions[target == cls]
            cls_pos = rng.permutation(cls_pos)
            take = max(1, int(len(cls_pos) * holdout_frac))
            hold_mask[cls_pos[:take]] = True
        holdout_idx = np.where(hold_mask)[0]
        train_idx = np.where(~hold_mask)[0]
    else:
        holdout_idx = shuffled[:n_hold]
        train_idx = shuffled[n_hold:]

    plan = SplitPlan(kind="random", train_idx=_positions(train_idx), holdout_idx=_positions(holdout_idx))

    rest = np.array(plan.train_idx)
    if entity_col and entity_col in df.columns:
        from sklearn.model_selection import GroupKFold
        groups = df.iloc[rest][entity_col].astype(str).to_numpy()
        n_groups = pd.Series(groups).nunique()
        k = 4 if n_groups >= 8 else 2
        gkf = GroupKFold(n_splits=k)
        folds = []
        for tr_pos, va_pos in gkf.split(rest, groups=groups):
            folds.append((_positions(rest[tr_pos]), _positions(rest[va_pos])))
        plan.cv = folds
        plan.kind = "group"
        calib = folds[-1][1]
    else:
        from sklearn.model_selection import KFold, StratifiedKFold
        y = target.iloc[rest]
        k = 5 if len(rest) >= 500 else 3
        splitter = (
            StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
            if task_type in ("binary", "multiclass") and y.nunique() >= 2
            else KFold(n_splits=k, shuffle=True, random_state=seed)
        )
        folds = []
        for tr_pos, va_pos in splitter.split(rest, y):
            folds.append((_positions(rest[tr_pos]), _positions(rest[va_pos])))
        plan.cv = folds
        plan.calib_idx = folds[-1][1]

    if not plan.calib_idx:
        plan.calib_idx = _positions(np.array(plan.train_idx)[-max(1, len(plan.train_idx) // 10):])
    plan.baseline = _baseline(target.iloc[train_idx], task_type)
    return plan


def _time_splits(df: pd.DataFrame, target_col: str, event_time_col: str | None, holdout_frac: float) -> SplitPlan:
    if not event_time_col:
        raise ValueError("Для прогноза временных рядов нужна колонка времени события")
    dt = pd.to_datetime(df[event_time_col], errors="coerce")
    order = np.argsort(dt.to_numpy(), kind="stable")
    n = len(order)
    n_hold = max(1, int(n * holdout_frac))
    holdout_idx = order[-n_hold:]
    train_idx = order[:-n_hold]
    plan = SplitPlan(kind="out_of_time", train_idx=_positions(train_idx), holdout_idx=_positions(holdout_idx))
    n_calib = max(1, int(len(train_idx) * 0.1))
    plan.calib_idx = _positions(train_idx[-n_calib:])
    plan.cv = _expanding_window(train_idx[:-n_calib])
    plan.info = {"event_time_col": event_time_col}
    plan.baseline = {"type": "naive", "detail": "naive: последнее известное значение"}
    return plan


def _expanding_window(core: np.ndarray, n_folds: int = 3) -> list[tuple[list[int], list[int]]]:
    if len(core) < 200:
        cut = int(len(core) * 0.75)
        return [(_positions(core[:cut]), _positions(core[cut:]))]
    chunks = np.array_split(core, n_folds + 1)
    folds = []
    for i in range(1, n_folds + 1):
        tr = np.concatenate(chunks[:i])
        va = chunks[i]
        folds.append((_positions(tr), _positions(va)))
    return folds


def _baseline(train_target: pd.Series, task_type: str) -> dict:
    if task_type in ("binary", "multiclass"):
        vc = train_target.value_counts(dropna=True)
        top = vc.index[0]
        rate = float(vc.iloc[0] / max(vc.sum(), 1))
        return {"type": "majority", "value": str(top), "detail": f"Наивный baseline: всегда предсказывать «{top}» (доля класса {rate:.1%})"}
    med = float(train_target.median())
    return {"type": "median", "value": med, "detail": f"Наивный baseline: всегда предсказывать медиану ({med:.2f})"}
