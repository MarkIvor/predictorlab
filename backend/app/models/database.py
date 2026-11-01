from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(24), default="")
    model_ids: Mapped[list] = mapped_column(JSON, default=list)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Connection(Base):
    __tablename__ = "connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    db_type: Mapped[str] = mapped_column(String(30))
    params_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(20), default="upload")
    file_path: Mapped[str] = mapped_column(Text, default="")
    nrows: Mapped[int] = mapped_column(Integer, default=0)
    ncols: Mapped[int] = mapped_column(Integer, default=0)
    columns_meta: Mapped[list] = mapped_column(JSON, default=list)
    event_time_col: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_col: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_hash: Mapped[str] = mapped_column(String(64), default="")
    connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feature_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    health: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Model(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str | None] = mapped_column(String(60), unique=True, nullable=True, index=True)
    public_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_type: Mapped[str] = mapped_column(String(20), default="binary")
    target_col: Mapped[str] = mapped_column(String(255))
    excluded_cols: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_matrix: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actionable: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guard_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schedule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    dir_path: Mapped[str] = mapped_column(Text, default="")
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    leakage_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guard_override: Mapped[bool] = mapped_column(Boolean, default=False)
    card_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(40), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class PredictionLog(Base):
    __tablename__ = "prediction_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int] = mapped_column(Integer, index=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(10), default="ui")
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    prediction_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    actual_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DriftReport(Base):
    __tablename__ = "drift_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(10), default="OK")
    psi_features: Mapped[dict] = mapped_column(JSON, default=dict)
    psi_prediction: Mapped[float | None] = mapped_column(Float, nullable=True)
    live_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Webhook(Base):
    __tablename__ = "webhooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    events: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def _connect_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def make_engine(db_url: str | None = None):
    url = db_url or get_settings().db_url
    eng = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(eng, "connect", _connect_pragma)
    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    from app.services.security import hash_password
    with engine.begin() as conn:
        from sqlalchemy import select as sa_select
        exists = conn.execute(sa_select(User.id).limit(1)).first()
        if not exists:
            s = get_settings()
            conn.execute(
                User.__table__.insert().values(
                    email=s.admin_email,
                    password_hash=hash_password(s.admin_password),
                    display_name="Админ",
                    role="admin",
                    must_change_password=True,
                )
            )
