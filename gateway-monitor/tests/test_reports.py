from datetime import datetime

from app.models.gateway_event import GatewayEvent
from app.services.reports import build_events_excel, build_events_pdf


def test_build_reports() -> None:
    event = GatewayEvent(
        id=1,
        created_at=datetime(2026, 7, 6, 9, 32, 41),
        event_type="state_change",
        busy_lines=1,
        idle_lines=7,
        duration=0,
        message="Linha 1: idle -> busy",
    )

    assert build_events_pdf([event]).startswith(b"%PDF")
    assert build_events_excel([event]).startswith(b"PK")
