from fastapi.testclient import TestClient
from pysnmp.hlapi import v1arch

from app.config import get_settings
from app.main import app
from app.services.snmp_client import PySnmpClient
from app.services.gateway_lines import normalize_line_status


def test_normalize_line_status() -> None:
    assert normalize_line_status("0") == "idle"
    assert normalize_line_status("1") == "busy"
    assert normalize_line_status("2") == "ringing"
    assert normalize_line_status("offline") == "unavailable"
    assert normalize_line_status(None) == "unknown"


def test_api_lines_returns_eight_lines() -> None:
    with TestClient(app) as client:
        response = client.get("/api/lines")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway_host"]
    assert len(payload["lines"]) == len(get_settings().monitored_line_numbers)


def test_snmp_symbolic_oid_identity_parsing() -> None:
    client = PySnmpClient(get_settings())
    identity = client._build_object_identity(
        v1arch,
        "GRANDSTREAM-MIB::lineStatus.1",
    )

    assert identity is not None
