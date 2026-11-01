import argparse
import os


def main():
    parser = argparse.ArgumentParser(prog="predictorlab-mcp", description="MCP-сервер PredictorLab")
    parser.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--url", default=os.environ.get("PREDICTORLAB_URL", "http://localhost:8000"),
                        help="База REST API PredictorLab")
    parser.add_argument("--api-key", default=os.environ.get("PREDICTORLAB_API_KEY", ""),
                        help="API-ключ pl_live_… (или переменная PREDICTORLAB_API_KEY)")
    parser.add_argument("--auth-token", default=os.environ.get("PREDICTORLAB_MCP_AUTH_TOKEN", ""),
                        help="Bearer-токен самого MCP-сервера (для http-транспорта)")
    args = parser.parse_args()

    os.environ["PREDICTORLAB_URL"] = args.url
    if args.api_key:
        os.environ["PREDICTORLAB_API_KEY"] = args.api_key

    from .server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    import starlette.middleware.base
    from starlette.responses import JSONResponse

    token = args.auth_token

    class BearerMiddleware(starlette.middleware.base.BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            header = request.headers.get("authorization", "")
            query_token = request.query_params.get("token", "")
            if token and header != f"Bearer {token}" and query_token != token:
                return JSONResponse({"detail": "Нужен Bearer-токен MCP"}, status_code=401)
            return await call_next(request)

    app = mcp.streamable_http_app()
    if args.transport == "sse":
        app = mcp.sse_app()
    app.add_middleware(BearerMiddleware)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
