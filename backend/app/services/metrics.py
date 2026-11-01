from prometheus_client import Counter, Histogram

PREDICT_REQUESTS = Counter("predictorlab_predict_requests_total", "Predictions", ["model_id", "mode"])
PREDICT_LATENCY = Histogram(
    "predictorlab_predict_latency_seconds",
    "Prediction latency",
    ["model_id"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
API_REQUESTS = Counter("predictorlab_api_requests_total", "HTTP requests", ["method", "path", "status"])
