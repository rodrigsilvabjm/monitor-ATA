from app.config import get_settings
from app.database import is_database_connected
from app.schemas.status import StatusResponse


def build_status_response() -> StatusResponse:
    settings = get_settings()
    return StatusResponse(
        status="online",
        database="connected" if is_database_connected() else "disconnected",
        version=settings.app_version,
    )
