import asyncio
import contextlib
import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import admin, auth, datasets, features, jobs, keys, models, monitor, predict, public, setup
from app.config import BASE_DIR, get_settings
from app.core.ingest.loader import IngestError
from app.jobs import queue
from app.models.database import init_db
from app.services.metrics import API_REQUESTS

logger = logging.getLogger("predictorlab")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    for noisy in ("uvicorn.access", "httpx", "optuna", "catboost", "lightgbm"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    setup_logging()
    queue.set_main_loop(asyncio.get_running_loop())
    logger.info("predictorlab started, storage=%s", get_settings().storage_path)
    from app.api.monitor import schedule_loop, ttl_cleanup_loop

    cleanup_task = asyncio.create_task(ttl_cleanup_loop())
    schedule_task = asyncio.create_task(schedule_loop())
    yield
    cleanup_task.cancel()
    schedule_task.cancel()
    queue.shutdown_pool()
    logger.info("predictorlab stopped")


app = FastAPI(title="PredictorLab", version="0.3.0", lifespan=lifespan)


@app.exception_handler(IngestError)
async def ingest_error_handler(request: Request, exc: IngestError):
    return JSONResponse({"detail": str(exc), **exc.hint}, status_code=exc.status)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error %s %s", request.method, request.url.path)
        response = JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)
    latency = (time.monotonic() - start) * 1000
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    API_REQUESTS.labels(request.method, path, response.status_code).inc()
    if not path.startswith("/api/metrics"):
        logger.info(
            "request",
            extra={"method": request.method, "path": path, "status": response.status_code, "latency_ms": round(latency)},
        )
    response.headers["x-latency-ms"] = str(round(latency))
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(datasets.router)
app.include_router(features.router)
app.include_router(models.router)
app.include_router(train_router := models.train_router)
app.include_router(predict.router)
app.include_router(jobs.router)
app.include_router(keys.router)
app.include_router(monitor.router)
app.include_router(public.router)
app.include_router(setup.router)


@app.get("/api/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "version": "0.3.0",
        "llm_enabled": s.llm_enabled,
        "signing_enabled": s.signing_enabled,
        "storage": str(s.storage_path),
    }


@app.get("/api/metrics")
def metrics():
    return Response(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


_frontend_dist = BASE_DIR / "frontend" / "dist"
if _frontend_dist.exists():
    from starlette.exceptions import HTTPException as StarletteHTTPException

    class SpaStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SpaStaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
