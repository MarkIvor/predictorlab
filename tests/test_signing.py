import json
from pathlib import Path

import pytest

from app.core.registry import artifacts
from app.config import get_settings


@pytest.fixture
def signed_env(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ARTIFACT_SIGNING_KEY", "test-signing-key-123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("ARTIFACT_SIGNING_KEY", raising=False)
    get_settings.cache_clear()


def _make_version(dir_path: Path):
    dir_path.mkdir(parents=True, exist_ok=True)
    artifacts.save_json(dir_path, "metrics.json", {"roc_auc": 0.9})
    artifacts.save_joblib(dir_path, "pipeline.joblib", {"kind": "linear"})
    artifacts.write_manifest(dir_path, {"model_id": 1, "version": 1})


def test_signed_artifact_passes(signed_env, tmp_path):
    vdir = tmp_path / "storage" / "models" / "1" / "v1"
    _make_version(vdir)
    ok, reason = artifacts.verify_version(vdir)
    assert ok, reason
    manifest = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("signed") is True
    assert "pipeline.joblib" in manifest["signatures"]


def test_tampered_artifact_rejected(signed_env, tmp_path):
    vdir = tmp_path / "storage" / "models" / "2" / "v1"
    _make_version(vdir)
    (vdir / "metrics.json").write_text('{"roc_auc": 0.99}', encoding="utf-8")
    ok, reason = artifacts.verify_version(vdir)
    assert not ok
    assert "metrics.json" in reason


def test_unsigned_import_rejected_when_signing_on(signed_env, tmp_path):
    vdir = tmp_path / "storage" / "models" / "3" / "v1"
    vdir.mkdir(parents=True)
    artifacts.save_joblib(vdir, "pipeline.joblib", {"kind": "linear"})
    artifacts.save_json(vdir, "manifest.json", {"model_id": 1})
    ok, reason = artifacts.verify_version(vdir)
    assert not ok


def test_verification_disabled_allows_own_storage(signed_env, tmp_path, monkeypatch):
    vdir = tmp_path / "storage" / "models" / "4" / "v1"
    _make_version(vdir)
    monkeypatch.setenv("ARTIFACT_SIGNING_KEY", "")
    get_settings.cache_clear()
    ok, reason = artifacts.verify_version(vdir)
    assert ok
