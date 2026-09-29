import asyncio
import secrets
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import ROOT, Settings
from .db import Database
from .github_source import GitHub
from .reclassify import reclassify_saved
from .routes import router
from .scheduler import scheduler
from .sync_service import SyncService


def create_app(settings=None, transport=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        import fcntl

        settings.data_dir.mkdir(parents=True, exist_ok=True)
        lock = (settings.data_dir / "instance.lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError("该数据目录已有一个运行实例，请勿启动多个 worker") from None
        try:
            db = Database(settings.data_dir / "hub.sqlite3")
            db.initialize()
            app.state.db, app.state.settings, app.state.csrf = (
                db,
                settings,
                secrets.token_urlsafe(32),
            )
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20, connect=8),
                transport=transport,
                limits=httpx.Limits(max_connections=2),
            ) as client:
                service = SyncService(db, GitHub(client, settings.token))
                reclassify_saved(db, service.classifier)
                service.recover()
                app.state.service = service
                tasks = [asyncio.create_task(service.worker())]
                if settings.auto_start:
                    tasks.append(asyncio.create_task(scheduler(service)))
                if not settings.token:
                    import logging

                    logging.getLogger("skill_hub").warning(
                        "未配置 GITHUB_TOKEN；公开采集可能受限，本地功能正常可用"
                    )
                try:
                    yield
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    service.recover()
        finally:
            lock.close()

    app = FastAPI(
        title="Research Skill Hub",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            token = request.headers.get("x-csrf-token", "")
            if (
                origin != expected
                or not secrets.compare_digest(token, getattr(request.app.state, "csrf", ""))
                or not token
            ):
                return JSONResponse({"detail": "同源校验失败，请刷新页面后重试"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "需要 JSON 请求"}, status_code=415)
            size = 0
            chunks = []
            async for chunk in request.stream():
                chunks.append(chunk)
                size += len(chunk)
                if size > 64000:
                    return JSONResponse({"detail": "请求过大"}, status_code=413)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    app.include_router(router)
    return app


def run():
    import uvicorn

    load_dotenv()
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    run()
