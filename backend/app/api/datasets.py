import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import get_settings
from app.core.ingest import io as ds_io
from app.core.ingest.loader import IngestError, ingest_dataframe, read_dataframe, sample_rows, stratified_sample
from app.models.database import Dataset, User
from app.services import pii as pii_service
from app.services.jsonsafe import json_safe

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class ColumnPatch(BaseModel):
    name: str
    type: str | None = None
    excluded: bool | None = None


class DatasetPatch(BaseModel):
    name: str | None = None
    event_time_col: str | None = None
    entity_col: str | None = None
    columns: list[ColumnPatch] | None = None


class SampleIn(BaseModel):
    nrows: int
    mode: str = "random"
    target_col: str | None = None
    name: str | None = None


def _dataset_out(d: Dataset, preview: list[dict] | None = None, mask_pii: bool = True) -> dict:
    pii_map = {c["name"]: c["pii"] for c in (d.columns_meta or []) if c.get("pii")}
    shown = preview
    if preview is not None:
        shown = [pii_service.mask_record(row, pii_map) if pii_map else row for row in preview]
        shown = json_safe(shown)
    return {
        "id": d.id,
        "name": d.name,
        "source_type": d.source_type,
        "nrows": d.nrows,
        "ncols": d.ncols,
        "columns": d.columns_meta or [],
        "health": d.health or {},
        "event_time_col": d.event_time_col,
        "entity_col": d.entity_col,
        "data_hash": d.data_hash,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        **({"preview": shown} if shown is not None else {}),
    }


def get_owned_dataset(dataset_id: str, user: User, db: Session) -> Dataset:
    d = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if d is None:
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if user.role != "admin" and d.user_id != user.id:
        raise HTTPException(status_code=403, detail="Датасет недоступен")
    return d


@router.post("/upload", status_code=201)
def upload(file: UploadFile = File(...), sheet: str | None = Form(None),
           sample_rows: int | None = Form(None), name: str | None = Form(None),
           user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    settings = get_settings()
    tmp_dir = settings.storage_path / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "data.csv").suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls", ".parquet"):
        raise IngestError("Поддерживаются форматы CSV, XLSX и Parquet")
    tmp_path = tmp_dir / f"upload_{secrets.token_hex(8)}{suffix}"
    try:
        with tmp_path.open("wb") as f:
            while chunk := file.file.read(1024 * 1024):
                f.write(chunk)
        try:
            df = read_dataframe(tmp_path, sheet)
        except IngestError:
            raise
        except Exception as exc:
            raise IngestError(f"Не удалось прочитать файл: {exc}")
        if sample_rows:
            df = sample_rows(df, sample_rows)
        dataset_id, nrows, ncols, columns_meta, data_hash, health = ingest_dataframe(df)
        d = Dataset(
            id=dataset_id,
            user_id=user.id,
            name=name or Path(file.filename or dataset_id).stem,
            source_type="upload",
            file_path=str((settings.datasets_path / dataset_id / "data.parquet").relative_to(settings.storage_path)),
            nrows=nrows,
            ncols=ncols,
            columns_meta=columns_meta,
            data_hash=data_hash,
            health=health,
        )
        db.add(d)
        db.commit()
        preview = ds_io.load_dataset_df(str(settings.storage_path / d.file_path)).head(20).to_dict(orient="records")
        return _dataset_out(d, preview)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("")
def list_datasets(user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    q = db.query(Dataset)
    if user.role != "admin":
        q = q.filter(Dataset.user_id == user.id)
    return [
        {
            "id": d.id, "name": d.name, "source_type": d.source_type, "nrows": d.nrows, "ncols": d.ncols,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in q.order_by(Dataset.created_at.desc()).all()
    ]


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, rows: int = 20,
                user: User = Depends(require_role("admin", "builder", "viewer")), db: Session = Depends(get_db)):
    d = get_owned_dataset(dataset_id, user, db)
    settings = get_settings()
    df = ds_io.load_dataset_df(str(settings.storage_path / d.file_path))
    preview = df.head(max(1, min(rows, 200))).to_dict(orient="records")
    return _dataset_out(d, preview)


@router.patch("/{dataset_id}")
def patch_dataset(dataset_id: str, body: DatasetPatch,
                  user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = get_owned_dataset(dataset_id, user, db)
    if body.name is not None:
        d.name = body.name
    if body.event_time_col is not None:
        d.event_time_col = body.event_time_col or None
    if body.entity_col is not None:
        d.entity_col = body.entity_col or None
    if body.columns:
        by_name = {c.name: c for c in body.columns}
        for col in d.columns_meta or []:
            patch = by_name.get(col["name"])
            if not patch:
                continue
            if patch.type:
                if patch.type not in ("numeric", "categorical", "datetime", "text", "boolean", "id"):
                    raise HTTPException(status_code=422, detail=f"Неизвестный тип колонки: {patch.type}")
                col["type"] = patch.type
                if patch.type in ("id", "constant"):
                    col["excluded"] = True
                    col["exclude_reason"] = "ID-подобная колонка" if patch.type == "id" else "константа"
                elif col.get("exclude_reason") in ("ID-подобная колонка", "константа"):
                    col["exclude_reason"] = None
            if patch.excluded is not None:
                col["excluded"] = patch.excluded
                if patch.excluded and not col.get("exclude_reason"):
                    col["exclude_reason"] = "исключена пользователем"
                if not patch.excluded:
                    col["exclude_reason"] = None
    db.commit()
    return _dataset_out(d)


@router.post("/{dataset_id}/sample", status_code=201)
def sample_dataset(dataset_id: str, body: SampleIn,
                   user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = get_owned_dataset(dataset_id, user, db)
    settings = get_settings()
    df = ds_io.load_dataset_df(str(settings.storage_path / d.file_path))
    if body.mode == "stratified":
        if not body.target_col:
            raise HTTPException(status_code=422, detail="Для стратифицированной выборки укажите таргет-колонку")
        df = stratified_sample(df, body.nrows, body.target_col)
    else:
        df = sample_rows(df, body.nrows)
    new_id, nrows, ncols, columns_meta, data_hash, health = ingest_dataframe(df)
    new = Dataset(
        id=new_id,
        user_id=user.id,
        name=body.name or f"{d.name} (выборка {body.nrows})",
        source_type=d.source_type,
        file_path=str((settings.datasets_path / new_id / "data.parquet").relative_to(settings.storage_path)),
        nrows=nrows,
        ncols=ncols,
        columns_meta=columns_meta,
        data_hash=data_hash,
        health=health,
    )
    db.add(new)
    db.commit()
    return _dataset_out(new)


@router.post("/{dataset_id}/dedupe", status_code=201)
def dedupe_dataset(dataset_id: str,
                    user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = get_owned_dataset(dataset_id, user, db)
    settings = get_settings()
    df = ds_io.load_dataset_df(str(settings.storage_path / d.file_path))
    before = len(df)
    id_cols = [c["name"] for c in (d.columns_meta or []) if c.get("type") == "id"]
    subset = [c for c in df.columns if c not in id_cols] or list(df.columns)
    df = df.drop_duplicates(subset=subset).reset_index(drop=True)
    new_id, nrows, ncols, columns_meta, data_hash, health = ingest_dataframe(df)
    health["deduped_from"] = before - nrows
    new = Dataset(
        id=new_id,
        user_id=user.id,
        name=f"{d.name} (без дубликатов)",
        source_type=d.source_type,
        file_path=str((settings.datasets_path / new_id / "data.parquet").relative_to(settings.storage_path)),
        nrows=nrows,
        ncols=ncols,
        columns_meta=columns_meta,
        data_hash=data_hash,
        health=health,
        event_time_col=d.event_time_col,
        entity_col=d.entity_col,
    )
    db.add(new)
    db.commit()
    return _dataset_out(new)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str,
                   user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = get_owned_dataset(dataset_id, user, db)
    settings = get_settings()
    import shutil
    shutil.rmtree(settings.storage_path / Path(d.file_path).parent, ignore_errors=True)
    db.delete(d)
    db.commit()
    return {"ok": True}
