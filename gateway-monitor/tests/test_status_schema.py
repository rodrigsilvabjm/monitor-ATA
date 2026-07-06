from app.schemas.status import StatusResponse


def test_status_response_schema() -> None:
    response = StatusResponse(
        status="online",
        database="connected",
        version="1.0.0",
    )

    assert response.model_dump() == {
        "status": "online",
        "database": "connected",
        "version": "1.0.0",
    }
