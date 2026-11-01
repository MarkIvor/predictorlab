from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.core.ingest.loader import read_dataframe
from app.core.predict import engine
from app.jobs.queue import is_cancel_requested
from app.models.database import Job, Model, ModelVersion, SessionLocal
from app.services.ensure import require


def _emit(job_id: str, ev_type: str, data: dict) -> None:
    from app.models.database import JobEvent

    db = SessionLocal()
    try:
        db.add(JobEvent(job_id=job_id, type=ev_type, data=data))
        db.commit()
    finally:
        db.close()


def _progress(job_id: str, **fields: object) -> None:
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


def run(job_id: str) -> dict:
    settings = get_settings()
    db = SessionLocal()
    job = require(db.get(Job, job_id), f"Задача {job_id} не найдена")
    payload = dict(job.payload or {})
    model = require(db.get(Model, job.model_id), "Модель не найдена")
    version = require(db.get(ModelVersion, payload.get("version_id") or model.active_version_id), "Версия не найдена")
    dir_rel = version.dir_path
    db.close()

    bundle = engine.load_bundle(version.id, dir_rel)
    input_path = Path(payload["input_path"])
    df = read_dataframe(input_path, None)

    schema_props = bundle["schema"]["input_schema"]["properties"]
    known = [c for c in df.columns if c in schema_props]
    if not known:
        raise RuntimeError("В файле нет ни одной колонки из схемы модели. Ожидаются: " + ", ".join(list(schema_props)[:10]))
    unknown = [c for c in df.columns if c not in schema_props]
    records = df[known].to_dict(orient="records")
    include_reasons = bool(payload.get("include_reasons"))
    threshold: float | None = payload.get("threshold")
    chunk = 5000
    out_rows: list[dict] = []
    done = 0
    for i in range(0, len(records), chunk):
        if is_cancel_requested(job_id):
            raise RuntimeError("cancelled")
        part = records[i : i + chunk]
        results, _ = engine.predict_records(bundle, part, threshold=threshold, include_reasons=False)
        for rec, res in zip(part, results, strict=False):
            row = {
                "prediction": res.get("prediction", res.get("label")),
                "probability": res.get("probability"),
                "interval_low": res.get("interval_low"),
                "interval_high": res.get("interval_high"),
                "ood": res.get("out_of_distribution", False),
            }
            for orig_col in df.columns:
                if orig_col in part[0]:
                    row[orig_col] = rec.get(orig_col)
            out_rows.append(row)
        done += len(part)
        _progress(job_id, done=done, total=len(records))
        _emit(job_id, "progress", {"done": done, "total": len(records)})

    out_df = pd.DataFrame(out_rows)

    if include_reasons and "probability" in out_df.columns and out_df["probability"].notna().any():
        top_n = min(settings.top_reason_rows, len(out_df))
        risky = out_df.sort_values("probability", ascending=False).head(top_n)
        reasons_map: dict[int, str] = {}
        risky_records = []
        risky_idx = []
        for idx in risky.index:
            rec = {c: out_df.at[idx, c] for c in known}
            risky_records.append(rec)
            risky_idx.append(idx)
        try:
            for j in range(0, len(risky_records), 200):
                part = risky_records[j : j + 200]
                idxs = risky_idx[j : j + 200]
                results, _ = engine.predict_records(bundle, part, threshold=threshold, include_reasons=True)
                for idx, res in zip(idxs, results, strict=False):
                    reasons_map[idx] = "; ".join(f"{r.get('text') or r.get('feature')}" for r in res.get("top_reasons", []))
                _progress(job_id, reasons_done=j + len(part), reasons_total=len(risky_records))
        except Exception:
            reasons_map = {}
        out_df["top_reasons"] = out_df.index.map(lambda i: reasons_map.get(i, ""))

    export_dir = settings.storage_path / "exports" / job_id
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_path = export_dir / "predictions.csv"
    xlsx_path: Path | None = export_dir / "predictions.xlsx"
    out_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        out_df.to_excel(xlsx_path, index=False)
    except Exception:
        xlsx_path = None
    input_path.unlink(missing_ok=True)

    _emit(job_id, "stage", {"stage": "done", "message": f"Готово: {len(out_df)} прогнозов"})
    return {
        "result_path": str(export_dir.relative_to(settings.storage_path)),
        "rows": int(len(out_df)),
        "unknown_columns": unknown,
        "files": {"csv": "predictions.csv", **({"xlsx": "predictions.xlsx"} if xlsx_path else {})},
    }
