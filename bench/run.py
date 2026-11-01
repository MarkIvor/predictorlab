"""Бенчмарк бюджетов производительности ТЗ §11.1.

Запуск: python bench/run.py [--port 8210] [--skip-full]
Поднимает изолированный инстанс (data-bench/, storage-bench/), прогоняет сценарии
и пишет BENCHMARKS.md в корень репозитория.
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def make_bench_data(n: int = 50_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame()
    for i in range(45):
        df[f"num_{i:02d}"] = rng.normal(0, 1, n).round(4)
    for i in range(4):
        df[f"cat_{i}"] = rng.choice([f"grp{a}" for a in "ABCDEFG"], n)
    df["event_date"] = pd.date_range("2024-01-01", periods=n, freq="min").round("D")
    logit = 0.8 * df["num_00"] + 0.5 * df["num_01"] - 0.4 * (df["cat_0"] == "grpA") + rng.normal(0, 0.5, n)
    df["target"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


def wait_health(client, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = client.get("/api/health")
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_job(client, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jr = client.get(f"/api/jobs/{job_id}").json()
        if jr["status"] in ("done", "error", "cancelled"):
            return jr
        time.sleep(2)
    return {"status": "timeout"}


def median(times: list[float]) -> float:
    return sorted(times)[len(times) // 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8210)
    parser.add_argument("--skip-full", action="store_true")
    args = parser.parse_args()
    base = f"http://localhost:{args.port}"

    data_dir = ROOT / "data-bench"
    storage_dir = ROOT / "storage-bench"
    for _attempt in range(3):
        for d in (data_dir, storage_dir):
            shutil.rmtree(d, ignore_errors=True)
        if not data_dir.exists() and not storage_dir.exists():
            break
        time.sleep(2)
    for d in (data_dir, storage_dir):
        d.mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "DATA_DIR": str(data_dir),
        "STORAGE_DIR": str(storage_dir),
        "ADMIN_EMAIL": "admin@predictorlab.io",
        "ADMIN_PASSWORD": "admin",
        "PYTHONIOENCODING": "utf-8",
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port)],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=open(ROOT / "bench-server.log", "w"),
        stderr=subprocess.STDOUT,
    )

    results: list[dict] = []
    try:
        client = httpx.Client(base_url=base, timeout=1800)
        assert wait_health(client), "сервер не поднялся"
        client.post("/api/auth/login", json={"email": "admin@predictorlab.io", "password": "admin"})

        print("Готовлю 50k×50…")
        df = make_bench_data()
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        r = client.post("/api/datasets/upload", files={"file": ("bench.csv", buf.getvalue().encode(), "text/csv")}, data={"name": "bench_50k"})
        assert r.status_code == 201, r.text[:300]
        ds_id = r.json()["id"]
        schema = client.get(f"/api/datasets/{ds_id}").json()
        {c["name"]: v for c, v in zip(schema["columns"], [], strict=False)} if False else None

        r = client.post("/api/models", json={"dataset_id": ds_id, "name": "bench_model", "target_col": "target", "event_time_col": "event_date"})
        assert r.status_code == 201, r.text[:300]
        model = r.json()
        mid = model["id"]
        if (model.get("guard_report") or {}).get("verdict") == "BLOCK":
            client.patch(f"/api/models/{mid}", json={"excluded_cols": model["guard_report"]["checks"][0].get("column", [])})

        print("Обучение quick…")
        t0 = time.monotonic()
        jr = wait_job(client, client.post(f"/api/models/{mid}/train", json={"mode": "quick"}).json()["job_id"], 1800)
        quick_sec = time.monotonic() - t0
        assert jr["status"] == "done", str(jr)[:300]
        results.append(
            {"op": "Обучение quick, 50k×50", "budget": "~1–2 мин", "value": f"{quick_sec:.1f}s", "ok": quick_sec < 240, "note": "бюджет v0.1 — ориентировочный"}
        )

        full_sec = None
        if not args.skip_full:
            print("Обучение full (бюджет по умолчанию 600 c)…")
            t0 = time.monotonic()
            jr = wait_job(client, client.post(f"/api/models/{mid}/train", json={"mode": "full"}).json()["job_id"], 2400)
            full_sec = time.monotonic() - t0
            assert jr["status"] == "done", str(jr)[:300]
            results.append(
                {
                    "op": "Обучение full, 50k×50",
                    "budget": "в пределах TRAIN_TIME_BUDGET_SEC=600",
                    "value": f"{full_sec:.1f}s",
                    "ok": full_sec <= 660,
                    "note": "Optuna CatBoost+LightGBM, поиск остановлен по таймеру",
                }
            )

        schema = client.get(f"/api/v1/models/{mid}/schema").json()
        example = schema.get("example") or {}
        rec = {}
        for k, p in schema["input_schema"]["properties"].items():
            v = example.get(k)
            if v is None:
                continue
            if p["type"] == "number":
                rec[k] = float(v)
            elif p["type"] == "boolean":
                rec[k] = str(v).lower() in ("true", "1", "да")
            else:
                rec[k] = str(v)

        print("Задержки predict…")
        no_reasons = []
        with_reasons = []
        for _ in range(5):
            t0 = time.monotonic()
            r = client.post(f"/api/v1/models/{mid}/predict", json={"data": [rec]})
            no_reasons.append((time.monotonic() - t0) * 1000)
            assert r.status_code == 200, r.text[:200]
            t0 = time.monotonic()
            r = client.post(f"/api/v1/models/{mid}/predict", json={"data": [rec], "include": ["reasons"]})
            with_reasons.append((time.monotonic() - t0) * 1000)
            assert r.status_code == 200, r.text[:200]
        results.append(
            {
                "op": "predict, 1 запись, без причин",
                "budget": "< 300 мс",
                "value": f"{median(no_reasons):.0f} мс (медиана)",
                "ok": median(no_reasons) < 300,
                "note": "",
            }
        )
        results.append(
            {
                "op": "predict + top_reasons (SHAP)",
                "budget": "< 1 с",
                "value": f"{median(with_reasons):.0f} мс (медиана)",
                "ok": median(with_reasons) < 1000,
                "note": "",
            }
        )

        print("Контрфактуал…")
        num_col = next((k for k, v in schema["input_schema"]["properties"].items() if v["type"] == "number"), None)
        client.patch(
            f"/api/models/{mid}",
            json={
                "actionable": {
                    num_col: {"min": float(min(rec.get(num_col, 0), 0)) - 5, "max": float(rec.get(num_col, 0)) + 5, "direction": "both", "cost_per_unit": 10}
                }
            },
        )
        client.post(f"/api/models/{mid}/profit", json={"benefit_tp": 50000, "action_cost": 1000, "fn_cost": 5000})
        t0 = time.monotonic()
        r = client.post(f"/api/v1/models/{mid}/counterfactual", json={"data": rec})
        cf_sec = time.monotonic() - t0
        results.append({"op": "counterfactual, 1 объект", "budget": "< 10 с (v0.2)", "value": f"{cf_sec:.2f}s", "ok": cf_sec < 10, "note": str(r.json())[:80]})

        print("Batch 10k…")
        cols = list(rec.keys())
        buf = io.StringIO()
        buf.write(",".join(cols) + "\n")
        for i in range(10_000):
            row = dict(rec)
            for c in cols:
                v = rec[c]
                row[c] = (v + (i % 7) * 0.01) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
            buf.write(",".join(str(row[c]) for c in cols) + "\n")
        t0 = time.monotonic()
        r = client.post(f"/api/v1/models/{mid}/predict/batch", files={"file": ("batch.csv", buf.getvalue().encode(), "text/csv")})
        assert r.status_code == 202, r.text[:200]
        jr = wait_job(client, r.json()["job_id"], 1800)
        batch_sec = time.monotonic() - t0
        assert jr["status"] == "done", str(jr)[:300]
        results.append(
            {
                "op": "Batch 10k строк, прогноз + интервалы",
                "budget": "< 2 мин (фоновая задача)",
                "value": f"{batch_sec:.1f}s",
                "ok": batch_sec < 120,
                "note": f"{jr['progress'].get('rows')} строк",
            }
        )

    finally:
        server.terminate()
        try:
            server.wait(15)
        except Exception:
            pass
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
        else:
            try:
                server.kill()
            except Exception:
                pass

    lines = [
        "# BENCHMARKS.md — измеренные бюджеты производительности",
        "",
        f"Дата замера: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · окружение: Windows, Python 3.12, CPU, без GPU",
        "Референс из ТЗ §11.1. Бюджеты — ориентиры для замера, не ворота приёмки (кроме §11.3).",
        "",
        "| Операция | Бюджет | Измерено | В бюджете | Комментарий |",
        "|---|---|---|---|---|",
    ]
    for res in results:
        mark = "✅" if res["ok"] else "⚠️ (issue, не блокер релиза)"
        lines.append(f"| {res['op']} | {res['budget']} | **{res['value']}** | {'да' if res['ok'] else 'нет — ' + mark} | {res['note']} |")
    lines += [
        "",
        "## Примечания",
        "- Все цифры посчитаны скриптом `bench/run.py` на демо-данных 50 000 строк × 50 колонок (синтетика с честным сигналом, seed фиксирован).",
        "- Conformal-покрытие на holdout измеряется в тестах приёмки (см. tests/), для дисбалансированных классов гарантируется одностороннее покрытие ≥ α (DECISIONS.md D-12).",
        "- При превышении бюджета более чем в 2 раза заводится issue, но релиз не блокируется (ТЗ §11).",
        "",
    ]
    (ROOT / "BENCHMARKS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=1))
    print("BENCHMARKS.md записан")


if __name__ == "__main__":
    main()
