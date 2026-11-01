import time

import pandas as pd

from app.config import get_settings
from app.core.business.counterfactual import find_counterfactual
from app.core.ingest.loader import read_dataframe
from app.core.predict import engine
from app.models.database import Job, Model, ModelVersion, SessionLocal
from app.jobs.queue import is_cancel_requested


def _progress(job_id, **fields):
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


def run(job_id: str):
    settings = get_settings()
    db = SessionLocal()
    job = db.get(Job, job_id)
    payload = dict(job.payload or {})
    model = db.get(Model, job.model_id)
    version = db.get(ModelVersion, payload.get("version_id") or model.active_version_id)
    db.close()

    bundle = engine.load_bundle(version.id, version.dir_path)
    input_path = settings.storage_path / payload["input_path"].replace(str(settings.storage_path), "").strip("\\/")
    df = read_dataframe(input_path, None)

    schema_props = bundle["schema"]["input_schema"]["properties"]
    known = [c for c in df.columns if c in schema_props]
    if not known:
        raise RuntimeError("В файле нет колонок из схемы модели")
    records = df[known].to_dict(orient="records")
    results, _ = engine.predict_records(bundle, records, threshold=model.threshold)

    threshold = model.threshold or 0.5
    actionable = model.actionable or {}
    cost_matrix = model.cost_matrix or {}
    rows = []
    checked = 0
    started = time.monotonic()
    limit = settings.playbook_max_rows
    for rec, res in zip(records, results):
        prob = res.get("probability")
        if prob is None or prob < threshold:
            continue
        checked += 1
        if checked > limit:
            break
        if is_cancel_requested(job_id):
            break
        cf = find_counterfactual(bundle, rec, actionable, threshold, direction="below",
                                 timeout=settings.cf_timeout_sec, cost_matrix=cost_matrix)
        entity = rec.get("entity_id") or rec.get(df.columns[0])
        base = {
            "entity": str(entity),
            "probability": round(prob, 4),
            "found": False,
        }
        if cf and not cf.get("already_ok"):
            roi = cf.get("expected_roi_rub")
            base.update({
                "found": True,
                "action": "; ".join(f"{f}: {old} → {new}" for f, new in cf["changes"].items()
                                    for old in [rec.get(f)]),
                "cost_rub": cf["cost_rub"],
                "probability_after": cf["probability_after"],
                "expected_roi_rub": roi,
                "recommendation": "Работать" if (roi or 0) > 0 else "Не трогать (отрицательный ROI)",
            })
        elif cf and cf.get("already_ok"):
            base.update({"found": True, "action": "Уже ниже порога", "cost_rub": 0,
                         "probability_after": cf["probability_after"], "expected_roi_rub": 0,
                         "recommendation": "Не требуется действие"})
        else:
            base.update({"action": "Действие в заданных рамках не найдено",
                         "recommendation": "Расширить границы управляемых признаков"})
        rows.append(base)
        if checked % 25 == 0:
            _progress(job_id, done=checked, total=min(limit, len(rows)))

    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(columns=["entity", "probability", "found", "action", "cost_rub",
                                    "probability_after", "expected_roi_rub", "recommendation"])
    elif "expected_roi_rub" in out.columns:
        out = out.sort_values("expected_roi_rub", ascending=False, na_position="last").reset_index(drop=True)

    export_dir = settings.storage_path / "exports" / job_id
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_path = export_dir / "playbook.csv"
    xlsx_path = export_dir / "playbook.xlsx"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        out.to_excel(xlsx_path, index=False)
    except Exception:
        xlsx_path = None

    from pathlib import Path
    try:
        Path(str(payload["input_path"])).unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "result_path": str(export_dir.relative_to(settings.storage_path)),
        "rows": int(len(out)),
        "checked": checked,
        "files": {"csv": "playbook.csv", **({"xlsx": "playbook.xlsx"} if xlsx_path else {})},
        "elapsed_sec": round(time.monotonic() - started, 1),
    }
