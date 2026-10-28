"""Local platform entry point; heavy graph models are not loaded at startup."""
import logging
import os
import time
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
try:
    from .store import Store
    from .platform_api import install_platform
    from .assistant_api import install_assistant
except ImportError:
    from store import Store
    from platform_api import install_platform
    from assistant_api import install_assistant

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("platform")


def create_app(db_path=None):
    app = FastAPI(title="拾物 · 客服咪电商社交平台", version="2.0.0")
    store = Store(db_path or os.getenv("PLATFORM_DB_PATH", str(ROOT / "data" / "runtime" / "platform.db")))
    app.state.store = store
    auth = install_platform(app, store)
    install_assistant(app, store, auth)
    app.mount("/static", StaticFiles(directory=ROOT / "src" / "web" / "static"), name="static")

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        rid, started = uuid.uuid4().hex[:12], time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        log.info("request=%s method=%s path=%s status=%s ms=%d", rid, request.method, request.url.path, response.status_code, (time.perf_counter()-started)*1000)
        return response

    @app.get("/")
    def index():
        return FileResponse(ROOT / "src" / "web" / "static" / "index.html")

    @app.get("/api/health")
    def health():
        with store.db() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "demo": True, "database": "sqlite", "ai_mode": os.getenv("AI_MODE", "local"), "model_configured": bool(os.getenv("DEEPSEEK_API_KEY")), "external_services_checked": False}

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
