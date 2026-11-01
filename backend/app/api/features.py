import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.core.features import builder
from app.jobs import queue
from app.models.database import Connection, Dataset, User
from app.services import pii as pii_service
from app.services import sql_guard

router = APIRouter(prefix="/api", tags=["features"])


class ConnectionIn(BaseModel):
    name: str = Field(min_length=1)
    db_type: str = Field(pattern="^(postgresql|mysql|clickhouse|sqlite)$")
    params: dict


class PreviewIn(BaseModel):
    table: str
    limit: int = 50
    sql: str | None = None


class BuildIn(BaseModel):
    name: str
    config: dict


def _own_connection(conn_id: int, user: User, db: Session) -> Connection:
    c = db.get(Connection, conn_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if user.role != "admin" and c.user_id != user.id:
        raise HTTPException(status_code=403, detail="Подключение недоступно")
    return c


def _conn_out(c: Connection) -> dict:
    return {"id": c.id, "name": c.name, "db_type": c.db_type, "created_at": c.created_at.isoformat()}


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    from app.services.security import encrypt_str

    c = Connection(
        user_id=user.id,
        name=body.name,
        db_type=body.db_type,
        params_enc=encrypt_str(json.dumps(body.params)),
    )
    db.add(c)
    db.commit()
    return _conn_out(c)


@router.get("/connections")
def list_connections(user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    q = db.query(Connection)
    if user.role != "admin":
        q = q.filter(Connection.user_id == user.id)
    return [_conn_out(c) for c in q.order_by(Connection.id.desc()).all()]


@router.delete("/connections/{conn_id}")
def delete_connection(conn_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    c = _own_connection(conn_id, user, db)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/connections/{conn_id}/test")
def test_connection(conn_id: int, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    c = _own_connection(conn_id, user, db)
    try:
        conn = builder.connection_connector(c)
        ok = conn.test()
        tables = conn.list_tables() if ok else []
        return {"ok": ok, "tables": tables[:500]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/connections/{conn_id}/preview")
def preview_table(conn_id: int, body: PreviewIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    c = _own_connection(conn_id, user, db)
    conn = builder.connection_connector(c)
    try:
        if body.sql:
            ok, reason = sql_guard.check_read_only(body.sql)
            if not ok:
                raise HTTPException(status_code=400, detail=reason)
            df = conn.execute_sql(body.sql, limit=max(1, min(body.limit, 1000)))
        else:
            if not body.table or not body.table.replace("_", "").isalnum():
                raise HTTPException(status_code=422, detail="Некорректное имя таблицы")
            df = conn.fetch_table(body.table, limit=max(1, min(body.limit, 1000)))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать таблицу: {exc}") from None
    records = df.head(200).to_dict(orient="records")
    pii_map = pii_service.scan_columns([{"name": col} for col in df.columns], records)
    records = [pii_service.mask_record(r, pii_map) for r in records]
    return {"columns": list(df.columns), "rows": records, "nrows": int(len(df))}


@router.post("/connections/{conn_id}/relations/{table}")
def propose_relations(conn_id: int, table: str, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    c = _own_connection(conn_id, user, db)
    conn = builder.connection_connector(c)
    fks = conn.foreign_keys(table)
    return {"foreign_keys": fks, "columns": conn.describe(table)}


@router.post("/features/build", status_code=202)
def build_features(body: BuildIn, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    config = body.config
    _own_connection(int(config.get("connection_id", 0)), user, db)
    for field in ("main_table", "main_key"):
        if not config.get(field):
            raise HTTPException(status_code=422, detail=f"В конфиге витрины не хватает поля «{field}»")
    for child in config.get("children", []):
        for field in ("table", "fk", "datetime_col"):
            if not child.get(field):
                raise HTTPException(status_code=422, detail=f"В дочерней таблице не хватает поля «{field}»")
    target = config.get("target") or {}
    if not target.get("table") or not target.get("datetime_col"):
        raise HTTPException(status_code=422, detail="Для витрины нужен таргет: таблица и datetime-колонка окна")
    job = queue.create_job("features_build", user_id=user.id, payload={"config": config, "name": body.name})
    queue.submit(job)
    return {"job_id": job.id, "status": job.status}


@router.get("/datasets/{dataset_id}/feature-sql")
def feature_sql(dataset_id: str, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = db.get(Dataset, dataset_id)
    if d is None or (user.role != "admin" and d.user_id != user.id):
        raise HTTPException(status_code=404, detail="Датасет не найден")
    return {"sql": d.feature_sql or "", "config": d.feature_config}


@router.post("/datasets/{dataset_id}/entity-preview")
def entity_preview(dataset_id: str, body: dict, user: User = Depends(require_role("admin", "builder")), db: Session = Depends(get_db)):
    d = db.get(Dataset, dataset_id)
    if d is None or (user.role != "admin" and d.user_id != user.id):
        raise HTTPException(status_code=404, detail="Датасет не найден")
    if d.source_type != "features" or not d.feature_config:
        raise HTTPException(status_code=400, detail="Датасет собран не из БД — вход по entity_id недоступен")
    entity_id = (body or {}).get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=422, detail="Укажите entity_id")
    try:
        df = builder.features_for_entities(d, [str(entity_id)])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось собрать фичи: {exc}") from None
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Сущность «{entity_id}» не найдена в источнике")
    from app.services.jsonsafe import json_safe

    return {"features": json_safe(df.iloc[0].to_dict()), "sql": d.feature_sql}
