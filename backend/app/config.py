from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    admin_email: str = "admin@predictorlab.io"
    admin_password: str = "admin"
    jwt_secret: str = ""
    encryption_key: str = ""

    storage_dir: str = "storage"
    data_dir: str = "data"

    max_rows: int = 500_000
    max_columns: int = 200

    train_time_budget_sec: int = 600
    deterministic: bool = False
    seed: int = 42
    quick_iterations: int = 500

    llm_base_url: str = ""
    llm_model: str = "deepseek/deepseek-v4-flash"
    llm_api_key: str = ""
    llm_allow_samples: bool = False

    cf_timeout_sec: float = 10.0
    playbook_max_rows: int = 1000
    top_reason_rows: int = 1000
    prediction_log_ttl_days: int = 180
    max_batch_rows: int = 100_000

    global_rate_limit_rpm: int = 120
    public_rate_limit_rpm: int = 30
    public_base_url: str = "http://localhost:3000"

    artifact_signing_key: str = ""
    tabpfn_enabled: bool = False

    drift_psi_warn: float = 0.1
    drift_psi_drift: float = 0.25
    retrain_check_minutes: int = 60

    mcp_auth_token: str = ""
    mcp_allow_train: bool = False

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.data_path / 'predictorlab.db').as_posix()}"

    @property
    def models_path(self) -> Path:
        return self.storage_path / "models"

    @property
    def datasets_path(self) -> Path:
        return self.storage_path / "datasets"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url)

    @property
    def signing_enabled(self) -> bool:
        return bool(self.artifact_signing_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_path.mkdir(parents=True, exist_ok=True)
    s.data_path.mkdir(parents=True, exist_ok=True)
    s.models_path.mkdir(parents=True, exist_ok=True)
    s.datasets_path.mkdir(parents=True, exist_ok=True)
    return s
