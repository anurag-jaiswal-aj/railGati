"""Health check endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from railgati import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    service: str
    version: str
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health status.

    This endpoint is deterministic and does not depend on
    external services. It confirms that the API process is
    running and responsive.
    """
    return HealthResponse(
        status="ok",
        service="railgati-api",
        version=__version__,
        timestamp=datetime.now(UTC).isoformat(),
    )
