from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.compare import router as compare_router
from app.api.demo import router as demo_router
from app.api.desk import router as desk_router
from app.api.excel import router as excel_router
from app.api.hiring import router as hiring_router
from app.api.problems import router as problems_router
from app.api.routes import router
from app.api.sourcing import router as sourcing_router
from app.config import get_settings
from app.db import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().validate_runtime()
    engine = make_engine()
    app.state.engine = engine
    app.state.sessions = make_session_factory(engine)
    yield
    engine.dispose()


_PUBLIC_PATHS = {"/health", "/openapi.json", "/docs", "/redoc"}


def create_app() -> FastAPI:
    app = FastAPI(title="HR Intelligence Hub", lifespan=lifespan)

    @app.middleware("http")
    async def require_credentials(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path in _PUBLIC_PATHS or path.startswith("/docs"):
            return await call_next(request)
        if not request.headers.get("authorization"):
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        try:
            return await call_next(request)
        except Exception:
            # An unhandled error would otherwise be answered by Starlette's outermost handler, which sits outside the
            # CORS middleware: the response carries no CORS headers, the browser discards it, and the screen can only
            # say "Network error" (the demo page said so for every one of 488 uploads). Answering here, inside CORS,
            # lets the browser read a real 500 and tell HR what happened.
            logging.getLogger("app").exception("unhandled error on %s %s", request.method, path)
            return JSONResponse(status_code=500, content={"detail": "server_error"})

    origins = [item.strip() for item in get_settings().cors_origins.split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(desk_router)
    app.include_router(hiring_router)
    app.include_router(sourcing_router)
    app.include_router(problems_router)
    app.include_router(excel_router)
    app.include_router(compare_router)
    if get_settings().environment == "local":
        app.include_router(demo_router)
    return app


app = create_app()
