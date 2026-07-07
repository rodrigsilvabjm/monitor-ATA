import asyncio

from fastapi.testclient import TestClient
from pysnmp.hlapi import v1arch

from app.config import get_settings
from app.services.gateway_lines import (
    GatewayLineMonitor,
    normalize_line_status,
    parse_busy_count,
)
from app.services.snmp_client import PySnmpClient


def test_normalize_line_status() -> None:
    assert normalize_line_status("0") == "idle"
    assert normalize_line_status("1") == "busy"
    assert normalize_line_status("2") == "ringing"
    assert normalize_line_status("offline") == "unavailable"
    assert normalize_line_status(None) == "unknown"


def test_parse_busy_count() -> None:
    assert parse_busy_count("3") == 3
    assert parse_busy_count("0") == 0
    assert parse_busy_count("-1") == 0
    assert parse_busy_count(None) == 0


def test_api_lines_returns_eight_lines() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/lines")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gateway_host"]
    assert len(payload["lines"]) == len(get_settings().monitored_line_numbers)


def test_asterisk_source_marks_specific_fxo_line() -> None:
    settings = get_settings().model_copy(
        update={
            "gateway_line_status_source": "asterisk",
            "gateway_monitored_lines": "1,2,3,4",
        }
    )
    monitor = GatewayLineMonitor(
        settings,
        active_line_provider=lambda: ({2}, True),
    )

    snapshot = asyncio.run(monitor.refresh_once())

    statuses = {line.line: line.status for line in snapshot.lines}
    assert statuses == {1: "idle", 2: "busy", 3: "idle", 4: "idle"}
    assert snapshot.lines[1].raw_value == "2"


def test_snmp_symbolic_oid_identity_parsing() -> None:
    client = PySnmpClient(get_settings())
    identity = client._build_object_identity(
        v1arch,
        "GRANDSTREAM-MIB::lineStatus.1",
    )

    assert identity is not None
