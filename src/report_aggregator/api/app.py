"""FastAPI application factory for the report-aggregator service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Origins allowed during local development (Next.js dev server).
DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    SECURITY: No authentication is configured. This service is intended for
    local development only.
    """
    app = FastAPI(
        title="Report Aggregator API",
        description="HTTP interface to the report-aggregator merge/edit engine.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    # Register feature routers.
    from report_aggregator.api.routes import router as reports_router

    app.include_router(reports_router)

    return app


app = create_app()
