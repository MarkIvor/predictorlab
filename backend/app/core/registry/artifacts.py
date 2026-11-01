import hashlib
import hmac
import json
from pathlib import Path

import joblib

from app.config import get_settings

ARTIFACT_NAMES = ("pipeline.joblib", "conformal.joblib", "ood.joblib", "schema.json",
                  "metrics.json", "leakage_report.json", "shap_background.parquet",
                  "feature_sql.sql", "holdout_preds.parquet", "manifest.json")


def version_dir(model_id: int, version: int) -> Path:
    s = get_settings()
    return s.models_path / str(model_id) / f"v{version}"


def _sign(path: Path, key: str) -> str:
    digest = hmac.new(key.encode("utf-8"), path.read_bytes(), hashlib.sha256).hexdigest()
    return digest


def save_joblib(dir_path: Path, name: str, obj) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / name
    joblib.dump(obj, path)
    return path


def save_json(dir_path: Path, name: str, data) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_joblib(path: Path):
    return joblib.load(path)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(dir_path: Path, manifest: dict) -> Path:
    s = get_settings()
    if s.signing_enabled:
        signatures = {}
        for f in dir_path.iterdir():
            if f.is_file() and f.name != "manifest.json":
                signatures[f.name] = _sign(f, s.artifact_signing_key)
        manifest["signatures"] = signatures
        manifest["signed"] = True
    manifest["storage_root"] = str(s.storage_path)
    return save_json(dir_path, "manifest.json", manifest)


def verify_version(dir_path: Path) -> tuple[bool, str]:
    s = get_settings()
    manifest_path = dir_path / "manifest.json"
    if not manifest_path.exists():
        return False, "manifest.json отсутствует"
    manifest = load_json(manifest_path)
    if not s.signing_enabled:
        return True, "подпись выключена, загрузка только из собственного storage"
    signatures = manifest.get("signatures") or {}
    if not signatures:
        return False, "артефакт не подписан текущим ключом — импорт запрещён"
    for name, sig in signatures.items():
        f = dir_path / name
        if not f.exists():
            return False, f"файл {name} отсутствует"
        if _sign(f, s.artifact_signing_key) != sig:
            return False, f"подпись файла {name} не совпадает — артефакт изменён или подменён"
    return True, "ok"
