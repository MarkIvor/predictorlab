import logging
import platform
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)

from app.config import get_settings
from app.core.business import profit as profit_mod
from app.core.explain import shap_explainer
from app.core.guard import checks as guard_checks
from app.core.ingest import io as ds_io
from app.core.registry import artifacts
from app.core.training import calibration as calib_mod
from app.core.training import candidates as cand
from app.core.training import preprocess as prep
from app.core.training import splits as splits_mod
from app.core.uncertainty import conformal as conf
from app.core.uncertainty import ood as ood_mod
from app.models.database import Dataset, Job, Model, ModelVersion, SessionLocal

logger = logging.getLogger("predictorlab.train")

METRIC_DIRECTION = {"binary": "maximize", "multiclass": "maximize", "regression": "minimize", "timeseries": "minimize"}


def _emit(job_id: str, ev_type: str, data: dict):
    from app.models.database import JobEvent

    db = SessionLocal()
    try:
        db.add(JobEvent(job_id=job_id, type=ev_type, data=data))
        db.commit()
    finally:
        db.close()


def _progress(job_id: str, **fields):
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            prog = dict(job.progress or {})
            prog.update(fields)
            job.progress = prog
            db.commit()
    finally:
        db.close()


def _cancelled(job_id: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        return bool(job and job.cancel_requested)
    finally:
        db.close()


def _lib_version(name: str) -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version(name)
    except Exception:
        return "unknown"


def _fit_predict(pipeline_kind: str, est, spec, X_tr, y_tr, X_va, task_type: str = "binary") -> np.ndarray:
    if pipeline_kind == "catboost":
        cat_idx = [X_tr.columns.get_loc(c) for c in spec.get("categorical", []) if c in X_tr.columns]
        est.fit(X_tr, y_tr, cat_features=cat_idx) if cat_idx else est.fit(X_tr, y_tr)
        if task_type == "regression":
            return np.asarray(est.predict(X_va)).reshape(-1, 1)
        return np.atleast_2d(est.predict_proba(X_va))
    if pipeline_kind == "lightgbm":
        X_tr_c, X_va_c = _lgbm_view(X_tr, spec), _lgbm_view(X_va, spec)
        est.fit(X_tr_c, y_tr, categorical_feature=spec.get("categorical") or "auto")
        if task_type == "regression":
            return np.asarray(est.predict(X_va_c)).reshape(-1, 1)
        return np.atleast_2d(est.predict_proba(X_va_c))
    est.fit(X_tr, y_tr)
    if task_type == "regression":
        return np.asarray(est.predict(X_va)).reshape(-1, 1)
    return np.atleast_2d(est.predict_proba(X_va))


def _lgbm_view(X: pd.DataFrame, spec: dict) -> pd.DataFrame:
    return cand.lgbm_view(X, spec)


def _estimator_predict_matrix(kind: str, est, spec, X: pd.DataFrame, task_type: str) -> np.ndarray:
    if task_type == "regression":
        if kind == "catboost":
            return est.predict(X)
        if kind == "lightgbm":
            return est.predict(_lgbm_view(X, spec))
        return est.predict(X)
    if kind == "catboost":
        return np.atleast_2d(est.predict_proba(X))
    if kind == "lightgbm":
        return np.atleast_2d(est.predict_proba(_lgbm_view(X, spec)))
    return np.atleast_2d(est.predict_proba(X))


def _fold_metric(task_type: str, y_true: np.ndarray, proba_or_pred: np.ndarray) -> float:
    if task_type == "binary":
        if len(np.unique(y_true)) < 2:
            return 0.5
        return float(roc_auc_score(y_true, proba_or_pred[:, 1]))
    if task_type == "multiclass":
        if len(np.unique(y_true)) < 2:
            return 0.0
        preds = np.argmax(proba_or_pred, axis=1)
        return float(f1_score(y_true, preds, average="macro"))
    return float(mean_squared_error(y_true, np.asarray(proba_or_pred).ravel()))


def run(job_id: str):
    settings = get_settings()
    db = SessionLocal()
    job = db.get(Job, job_id)
    payload = dict(job.payload or {})
    model = db.get(Model, job.model_id)
    dataset = db.get(Dataset, model.dataset_id)
    model_id, dataset_ref = model.id, model.dataset_id
    guard_pre = model.guard_report or {}
    cost_matrix = model.cost_matrix
    db.close()

    t_start = time.monotonic()
    mode = payload.get("mode", "quick")
    guard_override = bool(payload.get("guard_override"))
    task_type = model.task_type
    target_col = model.target_col

    if task_type == "timeseries":
        from app.core.training import ts

        ts.run(job_id, model_id, dataset_ref, mode)
        return

    df = ds_io.load_dataset_df(str(settings.storage_path / dataset.file_path))
    _emit(job_id, "stage", {"stage": "prepare", "message": f"Данные: {len(df)} строк"})

    mask = df[target_col].notna()
    df = df[mask].reset_index(drop=True)

    excluded = list(model.excluded_cols or [])
    spec = prep.build_feature_spec(dataset.columns_meta, target_col, excluded)
    X = prep.transform(df, spec)
    y, target_info = prep.encode_target(df[target_col], task_type)

    plan = splits_mod.make_splits(df, target_col, task_type, dataset.event_time_col, dataset.entity_col, seed=settings.seed)
    _emit(job_id, "stage", {"stage": "split", "message": f"Сплит: {plan.kind}", "split": plan.to_dict()})
    _progress(job_id, stage="split", split=plan.to_dict())

    split_guard = guard_checks.run_split_checks(
        df, prep.source_columns(spec), target_col, np.array(plan.train_idx), np.array(plan.holdout_idx), dataset.entity_col, split_kind=plan.kind
    )
    if split_guard["verdict"] == "BLOCK" and not guard_override:
        raise RuntimeError("Leakage Guard: BLOCK — " + "; ".join(c["detail"] for c in split_guard["checks"]))

    train_idx = np.array(plan.train_idx)
    holdout_idx = np.array(plan.holdout_idx)
    calib_idx = np.array(plan.calib_idx) if plan.calib_idx else train_idx[-max(1, len(train_idx) // 10) :]
    fit_idx = np.setdiff1d(train_idx, calib_idx)

    X_tr, _y_tr = X.iloc[fit_idx], y[fit_idx]
    X_cal, y_cal = X.iloc[calib_idx], y[calib_idx]
    X_ho, y_ho = X.iloc[holdout_idx], y[holdout_idx]

    candidates_results: list[dict] = []
    oof_store: dict[str, tuple] = {}

    def cv_evaluate(kind: str, est, spec_local, name: str, params: dict) -> dict:
        oof = np.full(len(y), np.nan)
        fold_metrics = []
        for _fold_no, (tr_i, va_i) in enumerate(plan.cv):
            if _cancelled(job_id):
                raise _Cancelled()
            tr_i, va_i = np.array(tr_i), np.array(va_i)
            if kind == "linear":
                est_fold = cand.build_linear(task_type, spec_local)
                proba = _fit_predict(kind, est_fold, spec_local, X.iloc[tr_i], y[tr_i], X.iloc[va_i], task_type)
            else:
                est_fold = _clone_est(kind, params, task_type)
                proba = _fit_predict(kind, est_fold, spec_local, X.iloc[tr_i], y[tr_i], X.iloc[va_i], task_type)
            if task_type == "regression":
                oof[va_i] = np.asarray(proba).ravel()
            else:
                oof[va_i] = np.asarray(proba)[:, -1]
            fold_metrics.append(_fold_metric(task_type, y[va_i], proba))
        cv_metric = float(np.mean(fold_metrics))
        candidates_results.append(
            {
                "name": name,
                "kind": kind,
                "params": _short_params(params),
                "cv_metric": cv_metric,
                "fold_metrics": [round(m, 6) for m in fold_metrics],
            }
        )
        oof_store[name] = (oof, params, kind)
        _emit(
            job_id,
            "candidate",
            {"candidate": name, "cv_metric": round(cv_metric, 6), "fold_metrics": [round(m, 6) for m in fold_metrics], "leaderboard": _leaderboard()},
        )
        _progress(job_id, leader=_leaderboard()[0] if candidates_results else None)
        return candidates_results[-1]

    def _leaderboard() -> list[dict]:
        board = sorted(candidates_results, key=lambda c: c["cv_metric"], reverse=(METRIC_DIRECTION[task_type] == "maximize"))
        return [{"name": c["name"], "cv_metric": round(c["cv_metric"], 6)} for c in board]

    linear_spec = prep.build_feature_spec(dataset.columns_meta, target_col, excluded)
    linear = cand.build_linear(task_type, linear_spec)
    try:
        cv_evaluate("linear", linear, linear_spec, "linear", {})
    except _Cancelled:
        raise
    except Exception as exc:
        logger.warning("linear candidate failed: %s", exc)

    if mode == "quick":
        cb_params = {
            "iterations": settings.quick_iterations,
            "depth": 6,
            "learning_rate": 0.1,
            "random_seed": settings.seed,
            "verbose": False,
            "thread_count": -1,
        }
        cb = cand.build_catboost(task_type, spec, cb_params)
        cand.fit_cat_levels(X_tr, spec)
        cv_evaluate("catboost", cb, spec, "catboost", cb_params)
    else:
        cand.fit_cat_levels(X_tr, spec)
        _run_optuna(job_id, task_type, spec, plan, X, y, settings, cv_evaluate)

    if settings.tabpfn_enabled:
        _maybe_tabpfn(job_id, task_type, X, y, plan, cv_evaluate)

    if _cancelled(job_id):
        raise _Cancelled()

    candidates_results.sort(key=lambda c: c["cv_metric"], reverse=(METRIC_DIRECTION[task_type] == "maximize"))
    if not candidates_results:
        raise RuntimeError("Ни один кандидат не обучился — проверьте данные")
    best = candidates_results[0]
    ensemble_info = None
    if len(candidates_results) >= 2 and task_type == "binary":
        a_name, b_name = candidates_results[0]["name"], candidates_results[1]["name"]
        oof_a, _, kind_a = oof_store[a_name]
        oof_b, _, kind_b = oof_store[b_name]
        best_w, best_metric = None, best["cv_metric"]
        mask = ~np.isnan(oof_a)
        if mask.sum() >= 100 and kind_a != "linear" and kind_b != "linear":
            for w in np.linspace(0.1, 0.9, 9):
                blended = w * oof_a[mask] + (1 - w) * oof_b[mask]
                if len(np.unique(y[mask])) < 2:
                    break
                metric = float(roc_auc_score(y[mask], blended))
                if metric > best_metric + 0.002:
                    if best_w is None or metric > best_metric:
                        best_w, best_metric = float(w), float(metric)
        if best_w is not None:
            ensemble_info = {"members": [a_name, b_name], "weights": [best_w, round(1 - best_w, 3)], "cv_metric": round(best_metric, 6)}
            _emit(job_id, "ensemble", {"ensemble": ensemble_info})

    _emit(job_id, "stage", {"stage": "final_fit", "message": "Финальное обучение"})
    pipeline, final_kind, final_params = _final_fit(task_type, spec, best, oof_store, ensemble_info, X.iloc[fit_idx], y[fit_idx])

    calibrator = None
    if task_type == "binary" and len(np.unique(y_cal)) >= 2:
        proba_raw = _proba_matrix(pipeline, final_kind, spec, X_cal, task_type, ensemble_info)[:, 1]
        method = payload.get("calibration", "auto")
        calibrator = calib_mod.fit_calibration(proba_raw, y_cal, method)
        proba_cal = calib_mod.apply_calibration(calibrator, proba_raw)
        _emit(
            job_id, "stage", {"stage": "calibration", "message": f"Калибровка: {calibrator.get('kind')}, Brier {calib_mod.brier_score(proba_cal, y_cal):.4f}"}
        )
    elif task_type == "binary":
        _emit(job_id, "stage", {"stage": "calibration", "message": "Калибровочный фолд содержит один класс — вероятности остаются некалиброванными"})

    _emit(job_id, "stage", {"stage": "uncertainty", "message": "Конформальные интервалы и OOD-детектор"})
    if task_type == "regression":
        preds_cal = (
            pipeline.predict(X_cal) if (ensemble_info or final_kind == "ensemble") else _estimator_predict_matrix(final_kind, pipeline, spec, X_cal, task_type)
        )
        conformal = conf.calibrate_regression(np.asarray(preds_cal).ravel(), y_cal, alpha=0.9)
        conformal["classes"] = None
    else:
        proba_full_cal = _proba_matrix(pipeline, final_kind, spec, X_cal, task_type, ensemble_info)
        if len(np.unique(y_cal)) >= 2:
            conformal = conf.calibrate_classification(proba_full_cal, y_cal.astype(int), alpha=0.9)
        else:
            conformal = {
                "alpha": 0.9,
                "q": 0.1,
                "method": "aps",
                "n_calib": len(y_cal),
                "k": proba_full_cal.shape[1],
                "degenerate": "калибровочный фолд содержит один класс",
            }

    num_cols = [c for c in spec["feature_cols"] if c not in spec.get("categorical", [])]
    ood = ood_mod.fit_ood(X_tr[num_cols].to_numpy(dtype=float), seed=settings.seed)

    _emit(job_id, "stage", {"stage": "evaluate", "message": "Оценка на holdout"})
    metrics, holdout_frame = _evaluate(
        task_type,
        pipeline,
        final_kind,
        spec,
        ensemble_info,
        calibrator,
        conformal,
        ood,
        X_ho,
        y_ho,
        df,
        holdout_idx,
        target_col,
        dataset,
        plan,
        num_cols,
        target_info,
    )

    _emit(job_id, "stage", {"stage": "explain", "message": "SHAP-объяснения"})
    X_bg_df = df.iloc[fit_idx]
    X_bg = prep.transform(X_bg_df, spec)
    bg = shap_explainer.make_background(X_bg, y[fit_idx], seed=settings.seed)
    try:
        shap_values = shap_explainer.shap_matrix(
            {"kind": "ensemble" if ensemble_info else final_kind, "estimator": pipeline, "spec": spec}, bg, X_ho.head(2000)
        )
        drivers = shap_explainer.global_drivers(shap_values, spec["feature_cols"])
        dependence = {f: shap_explainer.dependence_data(X_ho, shap_values, f) for f in [d["feature"] for d in drivers[:5]]}
    except Exception as exc:
        logger.warning("shap failed: %s", exc)
        shap_values, drivers, dependence = None, [], {}
    metrics["drivers"] = drivers
    metrics["dependence"] = dependence

    post_guard = guard_checks.run_post_checks(task_type, metrics, drivers)

    threshold_info = None
    cost_matrix = cost_matrix or None
    if task_type == "binary" and cost_matrix:
        threshold_info = profit_mod.compute_threshold(holdout_frame, cost_matrix)
        metrics["threshold_info"] = threshold_info

    used_sec = time.monotonic() - t_start

    db = SessionLocal()
    try:
        db_model = db.get(Model, model_id)
        db_dataset = db.get(Dataset, dataset_ref)
        prev = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).order_by(ModelVersion.version.desc()).first()
        version = (prev.version + 1) if prev else 1
        vdir = artifacts.version_dir(model_id, version)
        vdir.mkdir(parents=True, exist_ok=True)

        classes = target_info.get("classes")
        artifacts.save_joblib(
            vdir,
            "pipeline.joblib",
            {
                "kind": "ensemble" if ensemble_info else final_kind,
                "estimator": pipeline,
                "spec": spec,
                "task_type": task_type,
                "classes": classes,
                "calibrator": calibrator,
                "params": final_params,
                "members": ensemble_info["members"] if ensemble_info else None,
                "member_kinds": _member_kinds(ensemble_info, oof_store) if ensemble_info else None,
                "weights": ensemble_info["weights"] if ensemble_info else None,
            },
        )
        artifacts.save_joblib(vdir, "conformal.joblib", conformal)
        artifacts.save_joblib(vdir, "ood.joblib", ood)
        holdout_frame.to_parquet(vdir / "holdout_preds.parquet", index=False)
        bg.to_parquet(vdir / "shap_background.parquet", index=False)
        artifacts.save_json(vdir, "schema.json", _input_schema(dataset, spec, classes, df))
        artifacts.save_json(vdir, "metrics.json", metrics)
        leakage_report = {
            "pre": guard_pre,
            "split": split_guard,
            "post": post_guard,
            "verdict": _worst(guard_pre, split_guard, post_guard),
            "guard_override": guard_override,
        }
        artifacts.save_json(vdir, "leakage_report.json", leakage_report)
        if getattr(dataset, "feature_sql", None):
            (vdir / "feature_sql.sql").write_text(dataset.feature_sql, encoding="utf-8")
        manifest = {
            "model_id": model_id,
            "version": version,
            "task_type": task_type,
            "mode": mode,
            "seed": settings.seed,
            "deterministic": settings.deterministic,
            "data_hash": db_dataset.data_hash,
            "nrows": int(len(df)),
            "created_at": datetime.now(UTC).isoformat(),
            "split": plan.to_dict(),
            "candidates": candidates_results,
            "ensemble": ensemble_info,
            "budget_sec": settings.train_time_budget_sec if mode == "full" else None,
            "used_sec": round(used_sec, 1),
            "libraries": {lib: _lib_version(lib) for lib in ("fastapi", "scikit-learn", "catboost", "lightgbm", "optuna", "shap", "numpy", "pandas")},
            "python": platform.python_version(),
            "calibration": {"kind": calibrator["kind"]} if calibrator else None,
            "threshold": (threshold_info or {}).get("threshold"),
            "guard_override": guard_override,
        }
        artifacts.write_manifest(vdir, manifest)

        mv = ModelVersion(
            model_id=model_id,
            version=version,
            dir_path=str(vdir.relative_to(settings.storage_path)),
            manifest=manifest,
            metrics=metrics,
            leakage_report=leakage_report,
            guard_override=guard_override,
            status="ready",
        )
        db.add(mv)
        db.flush()
        from app.core.registry.modelcard import build_card_md

        mv.card_md = build_card_md(db_model, db_dataset, mv, metrics, manifest, leakage_report, threshold_info)
        db_model.status = "ready"
        db_model.active_version_id = mv.id
        if threshold_info:
            db_model.threshold = threshold_info["threshold"]
            db_model.threshold_info = threshold_info
        db.commit()
        version_row_id = mv.id
    finally:
        db.close()

    _emit(
        job_id,
        "stage",
        {
            "stage": "done",
            "message": "Модель обучена",
            "metrics": {k: v for k, v in metrics.items() if k in ("roc_auc", "pr_auc", "mae", "rmse", "r2", "coverage", "lift")},
            "version": version,
            "version_id": version_row_id,
        },
    )
    _progress(job_id, stage="done", version=version, metrics=metrics)
    return {"version": version, "version_id": version_row_id}


class _Cancelled(Exception):
    pass


def _clone_est(kind: str, params: dict, task_type: str):
    if kind == "catboost":
        return cand.build_catboost(task_type, None, params)
    if kind == "lightgbm":
        return cand.build_lightgbm(task_type, None, params)
    raise ValueError(kind)


def _short_params(p: dict) -> dict:
    out = {}
    for k, v in (p or {}).items():
        if isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
    return out


def _run_optuna(job_id, task_type, spec, plan, X, y, settings, cv_evaluate):
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    direction = METRIC_DIRECTION[task_type]

    def suggest_params(trial):
        family = trial.suggest_categorical("family", ["catboost", "lightgbm"])
        if family == "catboost":
            params = {
                "iterations": trial.suggest_int("iterations", 200, 800, step=100),
                "depth": trial.suggest_int("depth", 4, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.2, log=True),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0, log=True),
                "random_seed": settings.seed,
                "verbose": False,
                "thread_count": -1,
            }
        else:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 200, 800, step=100),
                "num_leaves": trial.suggest_int("num_leaves", 15, 127),
                "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.2, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
                "random_state": settings.seed,
                "verbose": -1,
                "n_jobs": -1,
            }
        return family, params

    def objective(trial):
        if _cancelled(job_id):
            raise _Cancelled()
        family, params = suggest_params(trial)
        est = _clone_est(family, params, task_type)
        result = cv_evaluate(family, est, spec, f"{family}_{trial.number}", params)
        return result["cv_metric"]

    budget = settings.train_time_budget_sec
    t0 = time.monotonic()
    stopped_by_timer = False

    def callback(study, trial):
        nonlocal stopped_by_timer
        if time.monotonic() - t0 > budget:
            stopped_by_timer = True
            study.stop()
        if _cancelled(job_id):
            study.stop()

    sampler = optuna.samplers.TPESampler(seed=settings.seed)
    study = optuna.create_study(direction=direction, sampler=sampler)
    try:
        study.optimize(objective, n_trials=60, timeout=max(10, budget - (time.monotonic() - t0)), callbacks=[callback], n_jobs=1)
    except _Cancelled:
        raise
    if stopped_by_timer:
        _emit(job_id, "stage", {"stage": "budget", "message": "Поиск остановлен по таймеру — берём лучший найденный кандидат"})
    _progress(job_id, stopped_by_timer=stopped_by_timer)


def _maybe_tabpfn(job_id, task_type, X, y, plan, cv_evaluate):
    try:
        from tabpfn import TabPFNClassifier
    except ImportError:
        _emit(job_id, "stage", {"stage": "tabpfn", "message": "TabPFN включён в настройках, но пакет не установлен"})
        return
    if task_type not in ("binary", "multiclass"):
        return
    n_features = len(X.columns)
    if len(y) > 10_000 or n_features > 500:
        return
    params = {"N_ensemble_configurations": 8}
    est = TabPFNClassifier(**params)
    try:
        cv_evaluate("tabpfn", est, {"categorical": []}, "tabpfn", params)
    except Exception as exc:
        logger.warning("tabpfn candidate failed: %s", exc)


def _final_fit(task_type, spec, best, oof_store, ensemble_info, X_fit, y_fit):
    if ensemble_info:
        members = []
        for name in ensemble_info["members"]:
            _, params, kind = oof_store[name]
            if kind == "linear":
                est = cand.build_linear(task_type, spec)
                est.fit(X_fit, y_fit)
            else:
                est = _clone_est(kind, params, task_type)
                if kind == "catboost":
                    cat_idx = [X_fit.columns.get_loc(c) for c in spec.get("categorical", []) if c in X_fit.columns]
                    est.fit(X_fit, y_fit, cat_features=cat_idx) if cat_idx else est.fit(X_fit, y_fit)
                elif kind == "lightgbm":
                    est.fit(_lgbm_view(X_fit, spec), y_fit, categorical_feature=spec.get("categorical") or "auto")
                else:
                    est.fit(X_fit, y_fit)
            members.append(est)
        ens = cand.EnsembleModel(
            members, ensemble_info["weights"], task_type, kinds=[oof_store[n][2] for n in ensemble_info["members"]], cat_levels=spec.get("cat_levels", {})
        )
        return ens, "ensemble", {"members": ensemble_info["members"], "weights": ensemble_info["weights"]}
    _, params, kind = oof_store[best["name"]]
    if kind == "linear":
        est = cand.build_linear(task_type, spec)
        est.fit(X_fit, y_fit)
        return est, kind, params
    est = _clone_est(kind, params, task_type)
    if kind == "catboost":
        cat_idx = [X_fit.columns.get_loc(c) for c in spec.get("categorical", []) if c in X_fit.columns]
        est.fit(X_fit, y_fit, cat_features=cat_idx) if cat_idx else est.fit(X_fit, y_fit)
    elif kind == "lightgbm":
        est.fit(_lgbm_view(X_fit, spec), y_fit, categorical_feature=spec.get("categorical") or "auto")
    else:
        est.fit(X_fit, y_fit)
    return est, kind, params


def _proba_matrix(pipeline, kind, spec, X, task_type, ensemble_info):
    if ensemble_info or kind == "ensemble":
        return pipeline.predict_proba(X)
    return _estimator_predict_matrix(kind, pipeline, spec, X, task_type)


def _member_kinds(ensemble_info, oof_store):
    return [oof_store[n][2] for n in ensemble_info["members"]]


def _evaluate(
    task_type, pipeline, kind, spec, ensemble_info, calibrator, conformal, ood, X_ho, y_ho, df, holdout_idx, target_col, dataset, plan, num_cols, target_info
):
    if task_type == "regression":
        preds = (
            pipeline.predict(X_ho)
            if (ensemble_info or kind == "ensemble")
            else np.asarray(_estimator_predict_matrix(kind, pipeline, spec, X_ho, task_type)).ravel()
        )
        mae = mean_absolute_error(y_ho, preds)
        rmse = float(np.sqrt(mean_squared_error(y_ho, preds)))
        r2 = r2_score(y_ho, preds)
        baseline = plan.baseline
        base_med = float(baseline.get("value", 0))
        base_mae = mean_absolute_error(y_ho, np.full_like(y_ho, base_med))
        mape = None
        if not np.any(np.abs(y_ho) < 1e-9):
            mape = float(np.mean(np.abs((y_ho - preds) / y_ho)) * 100)
        intervals = [conf.regression_interval(p, conformal) for p in preds]
        covered = np.array([lo <= yy <= hi for (lo, hi), yy in zip(intervals, y_ho, strict=False)])
        ood_flags = _ood_flags(ood, X_ho, num_cols)
        metrics = {
            "task_type": task_type,
            "mae": float(mae),
            "rmse": rmse,
            "r2": float(r2),
            "mape": mape,
            "baseline": baseline,
            "baseline_mae": float(base_mae),
            "lift_pct": round((base_mae - mae) / max(base_mae, 1e-9) * 100, 2),
            "coverage": float(covered.mean()),
            "coverage_target": conformal["alpha"],
            "n_holdout": int(len(y_ho)),
        }
        holdout_frame = pd.DataFrame(
            {
                "y_true": y_ho,
                "pred": preds,
                "interval_low": [i[0] for i in intervals],
                "interval_high": [i[1] for i in intervals],
                "ood": ood_flags,
            }
        )
    elif task_type == "binary":
        proba_raw = _proba_matrix(pipeline, kind, spec, X_ho, task_type, ensemble_info)[:, 1]
        proba = calib_mod.apply_calibration(calibrator, proba_raw) if calibrator else proba_raw
        classes = target_info.get("classes", ["0", "1"])
        sets = [conf.predict_set(np.array([1 - p, p]), conformal, ["0", "1"]) for p in proba_raw]
        covered = np.array([str(int(yy)) in s for yy, s in zip(y_ho, sets, strict=False)])
        preds = (proba >= 0.5).astype(int)
        auc = roc_auc_score(y_ho, proba_raw, labels=[0, 1]) if len(np.unique(y_ho)) >= 2 else 0.5
        pr_auc = average_precision_score(y_ho, proba_raw) if len(np.unique(y_ho)) >= 2 else 0.5
        ll = log_loss(y_ho, np.clip(proba, 1e-7, 1 - 1e-7), labels=[0, 1])
        brier = calib_mod.brier_score(proba, y_ho)
        precision = precision_score(y_ho, preds, zero_division=0)
        recall = recall_score(y_ho, preds, zero_division=0)
        base_rate = float(np.mean(y_ho))
        ood_flags = _ood_flags(ood, X_ho, num_cols)
        metrics = {
            "task_type": task_type,
            "roc_auc": float(auc),
            "pr_auc": float(pr_auc),
            "logloss": float(ll),
            "brier": float(brier),
            "precision": float(precision),
            "recall": float(recall),
            "baseline": plan.baseline,
            "lift": round(float(auc - 0.5), 4),
            "base_rate": base_rate,
            "coverage": float(covered.mean()),
            "coverage_target": conformal["alpha"],
            "reliability": calib_mod.reliability_curve(proba, y_ho),
            "n_holdout": int(len(y_ho)),
            "classes": classes,
        }
        holdout_frame = pd.DataFrame(
            {
                "y_true": y_ho.astype(int),
                "proba_raw": proba_raw,
                "proba": proba,
                "prediction_set": [",".join(str(c) for c in s) for s in sets],
                "ood": ood_flags,
            }
        )
    else:
        proba = _proba_matrix(pipeline, kind, spec, X_ho, task_type, ensemble_info)
        preds = np.argmax(proba, axis=1)
        acc = accuracy_score(y_ho, preds)
        f1m = f1_score(y_ho, preds, average="macro")
        ll = log_loss(y_ho, np.clip(proba, 1e-9, 1))
        sets = [conf.predict_set(row, conformal, [str(i) for i in range(proba.shape[1])]) for row in proba]
        covered = np.array([str(int(yy)) in s for yy, s in zip(y_ho, sets, strict=False)])
        ood_flags = _ood_flags(ood, X_ho, num_cols)
        metrics = {
            "task_type": task_type,
            "accuracy": float(acc),
            "macro_f1": float(f1m),
            "logloss": float(ll),
            "baseline": plan.baseline,
            "baseline_accuracy": float(max(np.bincount(y_ho.astype(int)) / len(y_ho))),
            "coverage": float(covered.mean()),
            "coverage_target": conformal["alpha"],
            "n_holdout": int(len(y_ho)),
            "classes": target_info.get("classes"),
        }
        holdout_frame = pd.DataFrame(
            {
                "y_true": y_ho.astype(int),
                "pred": preds,
                "prediction_set": [",".join(str(c) for c in s) for s in sets],
                "ood": ood_flags,
            }
        )
        for i in range(proba.shape[1]):
            holdout_frame[f"proba_{i}"] = proba[:, i]

    if dataset.entity_col and dataset.entity_col in df.columns:
        holdout_frame["entity"] = df.iloc[holdout_idx][dataset.entity_col].astype(str).to_numpy()
    if dataset.event_time_col and dataset.event_time_col in df.columns:
        holdout_frame["event_time"] = df.iloc[holdout_idx][dataset.event_time_col].astype(str).to_numpy()
    return metrics, holdout_frame


def _ood_flags(ood, X_ho, num_cols):
    try:
        scores = ood_mod.ood_scores(ood, X_ho[num_cols].to_numpy(dtype=float))
        return (scores < ood["threshold"]).tolist()
    except Exception:
        return [False] * len(X_ho)


def _worst(*reports: dict) -> str:
    verdict = "OK"
    for r in reports:
        v = (r or {}).get("verdict", "OK")
        if v == "BLOCK":
            return "BLOCK"
        if v == "WARN":
            verdict = "WARN"
    return verdict


def _input_schema(dataset, spec, classes, df) -> dict:
    meta_by_name = {c["name"]: c for c in dataset.columns_meta}
    properties = {}
    required = []
    example: dict = {}
    for col in spec["numeric"] + spec["boolean"] + spec["categorical"] + list(spec.get("datetime", {}).keys()):
        meta = meta_by_name.get(col, {})
        ctype = meta.get("type", "string")
        if ctype == "numeric":
            properties[col] = {"type": "number", "title": col}
        elif ctype == "boolean":
            properties[col] = {"type": "boolean", "title": col}
        elif ctype == "datetime":
            properties[col] = {"type": "string", "format": "date-time", "title": col}
        else:
            levels = (spec.get("cat_levels", {}).get(col) or [])[:200]
            properties[col] = {"type": "string", "title": col, **({"enum": levels} if levels else {})}
        sample = meta.get("sample") or []
        if sample:
            properties[col]["example"] = sample[0]
        example[col] = sample[0] if sample else None
    return {
        "input_schema": {"type": "object", "properties": properties, "required": required, "additionalProperties": True},
        "example": example,
        "target": {"column": spec["target_col"], "classes": classes},
    }
