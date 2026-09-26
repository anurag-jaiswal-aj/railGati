"""RailGati FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from railgati import __version__
from railgati.api.health import router as health_router
from railgati.common.logging import setup_logging
from railgati.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level)

    log = structlog.get_logger()

    app = FastAPI(
        title="RailGati API",
        description="Indian railway intelligence platform — discovery, planning & analytics.",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow the frontend origin only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health_router)

    log.info(
        "railgati_started",
        version=__version__,
        env=settings.env,
        host=settings.host,
        port=settings.port,
    )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "railgati.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
