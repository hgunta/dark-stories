"""Separate loopback-only development server. No app object for production startup."""

import argparse
from ipaddress import ip_address
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from .analytics_reporting import build_report
from .analytics_storage import SQLiteEventStore

ASSETS = Path(__file__).resolve().parent / "dashboard"


def create_dashboard(database_path, *, environment="test", mode="ai", port=8765):
    if environment not in ("test", "local") or mode not in ("ai", "offline"):
        raise ValueError("dashboard supports only explicit local/test data and ai/offline mode")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid local port")
    store = SQLiteEventStore(database_path)
    if not store.path.is_file():
        raise ValueError("an existing explicit analytics database file is required")
    app = FastAPI(title="Dark Stories local analytics", docs_url=None, redoc_url=None, openapi_url=None)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    @app.middleware("http")
    async def local_only(request, call_next):
        try:
            loopback = request.client is not None and ip_address(request.client.host).is_loopback
        except ValueError:
            loopback = False
        host = request.headers.get("host", "").lower()
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        # Host/Origin checks defend browser DNS rebinding and cross-origin local reads.
        if not loopback or host not in allowed_hosts or (origin is not None and origin != f"http://{host}") or fetch_site not in (None, "none", "same-origin"):
            response = JSONResponse({"detail": "Local access only"}, status_code=403)
        elif request.method not in ("GET", "HEAD"):
            response = JSONResponse({"detail": "Read-only dashboard"}, status_code=405)
        else:
            response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        })
        return response

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ASSETS / "index.html")

    @app.get("/dashboard.js", include_in_schema=False)
    def javascript():
        return FileResponse(ASSETS / "dashboard.js", media_type="text/javascript")

    @app.get("/dashboard.css", include_in_schema=False)
    def stylesheet():
        return FileResponse(ASSETS / "dashboard.css", media_type="text/css")

    @app.get("/api/report", include_in_schema=False)
    def report():
        try:
            # Single read-only snapshot; no offset paging across changing data.
            return build_report(store.snapshot(environment=environment), environment=environment, mode=mode)
        except (sqlite3.Error, ValueError):
            # No file paths, event payloads, exception strings, or schema diagnostics.
            return JSONResponse({"detail": "Report unavailable: check the local database format and 10000-event limit."}, status_code=503)

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="LOCAL-ONLY analytics dashboard (never bind or proxy publicly)")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--environment", choices=("test", "local"), default="test")
    parser.add_argument("--mode", choices=("ai", "offline"), default="ai")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    app = create_dashboard(args.database, environment=args.environment, mode=args.mode, port=args.port)
    import uvicorn
    # Fixed loopback bind; no --host, $PORT, forwarded headers, or public proxy trust.
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
