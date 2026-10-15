from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text

from kitframe.api.routers import (
    assets,
    auth,
    brand,
    generations,
    health,
    jobs,
    library,
    notifications,
    products,
    projects,
    rights,
    search,
    tools,
    uploads,
)
from kitframe.db.session import engine
from kitframe.errors import AppError, ErrorCode
from kitframe.settings import get_settings

REQUEST_COUNT = Counter("kitframe_http_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_LATENCY = Histogram("kitframe_http_request_duration_seconds", "HTTP latency", ["route"])

logger = logging.getLogger("kitframe")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Kitframe API",
        version="4.1.0",
        default_response_class=ORJSONResponse,
        docs_url="/api/v1/docs" if settings.app_env != "production" else None,
        openapi_url="/api/v1/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_error", extra={"request_id": request_id})
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": ErrorCode.INTERNAL_ERROR,
                        "message": "Internal server error",
                        "details": {},
                    }
                },
            )
        elapsed = time.perf_counter() - start
        route = request.url.path
        REQUEST_LATENCY.labels(route=route).observe(elapsed)
        REQUEST_COUNT.labels(method=request.method, route=route, status=str(response.status_code)).inc()
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    api = "/api/v1"
    app.include_router(health.router, prefix=api)
    app.include_router(auth.router, prefix=api)
    app.include_router(brand.router, prefix=api)
    app.include_router(projects.router, prefix=api)
    app.include_router(products.router, prefix=api)
    app.include_router(assets.router, prefix=api)
    app.include_router(generations.router, prefix=api)
    app.include_router(library.router, prefix=api)
    app.include_router(rights.router, prefix=api)
    app.include_router(notifications.router, prefix=api)
    app.include_router(jobs.router, prefix=api)
    app.include_router(search.router, prefix=api)
    app.include_router(uploads.router, prefix=api)
    app.include_router(tools.router, prefix=api)

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        token = request.query_params.get("token") or request.headers.get("X-Metrics-Token")
        if token != settings.metrics_token:
            raise AppError(ErrorCode.UNAUTHORIZED, "Invalid metrics token", status_code=401)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.on_event("startup")
    async def startup() -> None:
        settings.validate_providers()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    return app


app = create_app()
