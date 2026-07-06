from fastapi.testclient import TestClient

from app.main import app


def test_prometheus_metrics_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "gateway_monitor_busy_lines" in response.text
