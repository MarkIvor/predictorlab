import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import get_settings
from app.core.business import profit as profit_mod
from app.core.guard import checks as guard_checks
from app.core.ingest import io as ds_io
from app.core.training import preprocess as prep
from app.core.training.splits import make_splits
from app.jobs import queue
from app.models.database import Dataset, Model, ModelVersion, User

router = APIRouter(prefix="/api/models", tags=["models"])
train_router = APIRouter()


class ModelCreateIn(BaseModel):
    dataset_id: str
    name: str = Field(min_length=1, max_length=120)
    target_col: str
    task_type: str | None = Field(default=None, pattern="^(binary|regression|multiclass|timeseries)$")
    event_time_col: str | None = None
    entity_col: str | None = None


class ModelPatchIn(BaseModel):
    name: str | None = None
    excluded_cols: list[str] | None = None
    event_time_col: str | None = None
    entity_col: str | None = None
    cost_matrix: dict | None = None
    actionable: dict | None = None
    schedule: dict | None = None


class TrainIn(BaseModel):
    mode: str = Field(default="quick", pattern="^(quick|full)$")
    guard_override: bool = False
    calibration: str = Field(default="auto", pattern="^(auto|isotonic|platt|none)$")


class RollbackIn(BaseModel):
    version: int


def get_owned_model(model_id: int, user: User, db: Session) -> Model:
    m = db.get(Model, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    if user.role != "admin" and m.user_id != user.id:
        raise HTTPException(status_code=403, detail="Модель недоступна")
    return m


def detect_task_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if pd.api.types.is_numeric_dtype(non_null) and non_null.nunique() > 10:
        return "regression"
    nunique = non_null.nunique()
    if nunique == 2:
        return "binary"
    if pd.api.types.is_numeric_dtype(non_null) and nunique > 2:
        return "regression"
    if nunique <= 10:
        return "multiclass"
    return "regression"


def run_health(m: Model, dataset: Dataset, db: Session) -> dict:
    settings = get_settings()
    df = ds_io.load_dataset_df(str(settings.storage_path / dataset.file_path))
    df = df[df[m.target_col].notna()].reset_index(drop=True)
    task_type = m.task_type
    if task_type != "timeseries":
        report = guard_checks.run_pre_checks(
            df, m.target_col, task_type, dataset.event_time_col, dataset.entity_col, dataset.columns_meta, m.excluded_cols or []
        )
        spec = prep.build_feature_spec(dataset.columns_meta, m.target_col, m.excluded_cols or [])
        if len(df) > 200:
            plan = make_splits(df, m.target_col, task_type, dataset.event_time_col, dataset.entity_col, seed=settings.seed)
            split_guard = guard_checks.run_split_checks(
                df, prep.source_columns(spec), m.target_col, np.array(plan.train_idx), np.array(plan.holdout_idx), dataset.entity_col, split_kind=plan.kind
            )
            report["checks"] = (report.get("checks") or []) + split_guard["checks"]
            report["split_kind"] = plan.kind
            if split_guard["verdict"] == "BLOCK":
                report["verdict"] = "BLOCK"
            elif split_guard["verdict"] == "WARN" and report["verdict"] == "OK":
                report["verdict"] = "WARN"
        else:
            report["split_kind"] = "random"
    else:
        report = {"verdict": "OK", "checks": [], "exclude_auto": {}, "split_kind": "out_of_time"}
    m.guard_report = report
    db.commit()
    return report


def _model_out(m: Model, db: Session, detailed: bool = False) -> dict:
    version = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    dataset = db.get(Dataset, m.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Датасет модели не найден")
    metrics = (version.metrics if version else None) or {}
    hero = metrics.get("roc_auc") or metrics.get("mae") or metrics.get("accuracy")
    out = {
        "id": m.id,
        "name": m.name,
        "status": m.status,
        "task_type": m.task_type,
        "target_col": m.target_col,
        "dataset": {"id": dataset.id, "name": dataset.name, "nrows": dataset.nrows, "ncols": dataset.ncols},
        "excluded_cols": m.excluded_cols or [],
        "event_time_col": dataset.event_time_col if dataset else None,
        "entity_col": dataset.entity_col if dataset else None,
        "guard_verdict": (m.guard_report or {}).get("verdict", "OK"),
        "threshold": m.threshold,
        "active_version": version.version if version else None,
        "hero_metric": hero,
        "profit_scaled": ((m.threshold_info or {}) or {}).get("profit_scaled"),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
    if detailed:
        out["guard_report"] = m.guard_report
        out["cost_matrix"] = m.cost_matrix
        out["threshold_info"] = m.threshold_info
        out["actionable"] = m.actionable
        out["schedule"] = m.schedule
        out["metrics"] = version.metrics if version else None
        out["versions"] = [
            {
                "id": v.id,
                "version": v.version,
                "status": v.status,
                "created_at": v.created_at.isoformat(),
                "guard_verdict": ((v.leakage_report or {}).get("verdict")),
            }
            for v in db.query(ModelVersion).filter(ModelVersion.model_id == m.id).order_by(ModelVersion.version).all()
        ]
    return out


@router.get("")
def list_models(user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    q = db.query(Model)
    if user.role != "admin":
        q = q.filter(Model.user_id == user.id)
    return [_model_out(m, db) for m in q.order_by(Model.created_at.desc()).all()]


@router.post("", status_code=201)
def create_model(body: ModelCreateIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if user.role != "admin" and dataset.user_id != user.id:
        raise HTTPException(status_code=403, detail="Датасет недоступен")
    if body.target_col not in [c["name"] for c in dataset.columns_meta]:
        raise HTTPException(status_code=422, detail=f"Колонки «{body.target_col}» нет в датасете")

    settings = get_settings()
    df = ds_io.load_dataset_df(str(settings.storage_path / dataset.file_path))
    target = df[body.target_col].dropna()
    if len(target) < settings.max_rows * 0 + 30:
        if len(target) < 30:
            raise HTTPException(status_code=422, detail="В таргете меньше 30 заполненных значений — обучиться не на чем")
    task_type = body.task_type or detect_task_type(target)
    if task_type == "timeseries" and not body.event_time_col:
        raise HTTPException(status_code=422, detail="Для прогноза временных рядов укажите колонку времени")

    if body.event_time_col:
        dataset.event_time_col = body.event_time_col
    if body.entity_col:
        dataset.entity_col = body.entity_col
    db.commit()

    m = Model(
        user_id=user.id,
        dataset_id=dataset.id,
        name=body.name,
        task_type=task_type,
        target_col=body.target_col,
        status="draft",
    )
    db.add(m)
    db.commit()
    run_health(m, dataset, db)
    return _model_out(m, db, detailed=True)


@router.get("/{model_id}")
def get_model(model_id: int, user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    return _model_out(m, db, detailed=True)


@router.patch("/{model_id}")
def patch_model(model_id: int, body: ModelPatchIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    if body.name is not None:
        m.name = body.name
    if body.excluded_cols is not None:
        m.excluded_cols = body.excluded_cols
    if body.cost_matrix is not None:
        m.cost_matrix = body.cost_matrix
        if m.task_type == "binary" and m.active_version_id:
            _recompute_threshold(m, db)
    if body.actionable is not None:
        m.actionable = body.actionable
    if body.schedule is not None:
        m.schedule = body.schedule or None
    if body.event_time_col is not None or body.entity_col is not None:
        dataset = db.get(Dataset, m.dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Датасет не найден")
        if body.event_time_col is not None:
            dataset.event_time_col = body.event_time_col or None
        if body.entity_col is not None:
            dataset.entity_col = body.entity_col or None
    db.commit()
    return _model_out(m, db, detailed=True)


def _recompute_threshold(m: Model, db: Session):
    settings = get_settings()
    version = db.get(ModelVersion, m.active_version_id)
    if not version or not m.cost_matrix:
        return
    ho_path = settings.storage_path / version.dir_path / "holdout_preds.parquet"
    if not ho_path.exists():
        return
    ho = pd.read_parquet(ho_path)
    if "proba" not in ho.columns:
        return
    info = profit_mod.compute_threshold(ho, m.cost_matrix)
    m.threshold = info["threshold"]
    m.threshold_info = info
    metrics = dict(version.metrics or {})
    metrics["threshold_info"] = info
    version.metrics = metrics


@router.post("/{model_id}/recheck")
def recheck_model(model_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    dataset = db.get(Dataset, m.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    report = run_health(m, dataset, db)
    return report


@router.post("/{model_id}/train", status_code=201)
def train_model(model_id: int, body: TrainIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    if m.status == "training":
        raise HTTPException(status_code=409, detail="Модель уже обучается")
    verdict = (m.guard_report or {}).get("verdict", "OK")
    if verdict == "BLOCK" and not body.guard_override:
        raise HTTPException(
            status_code=400, detail="Leakage Guard вернул BLOCK. Исключите проблемные колонки или подтвердите снятие блокировки (guard_override)"
        )
    m.status = "training"
    db.commit()
    job = queue.create_job(
        "train",
        user_id=user.id,
        model_id=m.id,
        dataset_id=m.dataset_id,
        payload={"mode": body.mode, "guard_override": body.guard_override, "calibration": body.calibration},
    )
    queue.submit(job)
    return {"job_id": job.id, "status": job.status}


@router.delete("/{model_id}")
def delete_model(model_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    import shutil

    m = get_owned_model(model_id, user, db)
    settings = get_settings()
    shutil.rmtree(settings.models_path / str(m.id), ignore_errors=True)
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.post("/{model_id}/rollback")
def rollback_model(model_id: int, body: RollbackIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    version = db.query(ModelVersion).filter(ModelVersion.model_id == m.id, ModelVersion.version == body.version).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Версия не найдена")
    m.active_version_id = version.id
    m.status = "ready"
    db.commit()
    return {"ok": True, "active_version": version.version}


@router.post("/{model_id}/profit")
def set_profit(model_id: int, body: dict, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    m.cost_matrix = body
    if m.task_type == "binary":
        _recompute_threshold(m, db)
    elif m.task_type == "regression" and m.active_version_id:
        settings = get_settings()
        version = db.get(ModelVersion, m.active_version_id)
        if version is None:
            return
        ho_path = settings.storage_path / version.dir_path / "holdout_preds.parquet"
        if ho_path.exists():
            info = profit_mod.regression_cost(pd.read_parquet(ho_path), body)
            m.threshold_info = info
    db.commit()
    return m.threshold_info or {"detail": "Матрица стоимостей сохранена"}


@router.get("/{model_id}/card")
def model_card(model_id: int, user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    return {"card_md": v.card_md or "", "version": v.version, "llm_narrative": (v.metrics or {}).get("llm_narrative")}


@router.post("/{model_id}/card/regenerate")
def regenerate_card(model_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None:
        raise HTTPException(status_code=400, detail="Модель ещё не обучена")
    from app.core.guard import llm_judge

    fields = {
        "name": m.name,
        "task_type": m.task_type,
        "target": m.target_col,
        "roc_auc": (v.metrics or {}).get("roc_auc"),
        "mae": (v.metrics or {}).get("mae"),
        "coverage": (v.metrics or {}).get("coverage"),
        "drivers": ", ".join(d["feature"] for d in ((v.metrics or {}).get("drivers") or [])[:5]),
        "baseline": (v.manifest or {}).get("split", {}).get("baseline", {}).get("detail"),
        "threshold_profit": (m.threshold_info or {}).get("profit"),
    }
    result = llm_judge.card_narrative(fields)
    if result is None:
        raise HTTPException(status_code=400, detail="LLM недоступна или текст не прошёл проверку чисел — карточка оставлена по шаблону")
    text, _ = result
    metrics = dict(v.metrics or {})
    metrics["llm_narrative"] = text
    v.metrics = metrics
    db.commit()
    return {"llm_narrative": text}


@router.get("/{model_id}/card/export")
def export_card(model_id: int, format: str = "md", user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    m = get_owned_model(model_id, user, db)
    v = db.get(ModelVersion, m.active_version_id) if m.active_version_id else None
    if v is None or not v.card_md:
        raise HTTPException(status_code=400, detail="Карточка ещё не создана")
    if format == "pdf":
        from fastapi.responses import FileResponse

        from app.core.registry.pdf import card_pdf

        path = card_pdf(m, v)
        return FileResponse(path, filename=f"model_card_{m.id}_v{v.version}.pdf", media_type="application/pdf")
    from fastapi.responses import Response

    return Response(
        v.card_md, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="model_card_{m.id}_v{v.version}.md"'}
    )
