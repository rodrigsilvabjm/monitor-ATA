from fastapi import APIRouter

from app.schemas.status import StatusResponse
from app.services.status import build_status_response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=StatusResponse)
def health_check() -> StatusResponse:
    return build_status_response()
