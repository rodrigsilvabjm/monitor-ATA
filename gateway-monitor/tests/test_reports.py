from datetime import datetime

from app.models.gateway_event import GatewayEvent
from app.services.reports import (
    build_events_excel,
    build_events_pdf,
    build_report_summary,
    report_summary_to_dict,
)


def test_build_reports() -> None:
    events = [
        GatewayEvent(
            id=1,
            created_at=datetime(2026, 7, 6, 9, 32, 41),
            event_type="state_change",
            busy_lines=1,
            idle_lines=3,
            duration=0,
            message="Linha 1: idle -> busy",
        ),
        GatewayEvent(
            id=2,
            created_at=datetime(2026, 7, 6, 9, 42, 41),
            event_type="state_change",
            busy_lines=0,
            idle_lines=4,
            duration=0,
            message="Linha 1: busy -> idle",
        ),
        GatewayEvent(
            id=3,
            created_at=datetime(2026, 7, 6, 10, 0, 0),
            event_type="congestion_end",
            busy_lines=3,
            idle_lines=1,
            duration=120,
            message="Fim de congestionamento",
        ),
    ]

    assert build_events_pdf(events).startswith(b"%PDF")
    assert build_events_excel(events).startswith(b"PK")


def test_build_report_summary() -> None:
    events = [
        GatewayEvent(
            id=1,
            created_at=datetime(2026, 7, 7, 9, 0, 0),
            event_type="state_change",
            busy_lines=1,
            idle_lines=3,
            duration=0,
            message="Linha 1: idle -> busy",
        ),
        GatewayEvent(
            id=2,
            created_at=datetime(2026, 7, 7, 9, 5, 0),
            event_type="state_change",
            busy_lines=2,
            idle_lines=2,
            duration=0,
            message="Linha 2: idle -> busy",
        ),
        GatewayEvent(
            id=3,
            created_at=datetime(2026, 7, 7, 9, 15, 0),
            event_type="state_change",
            busy_lines=1,
            idle_lines=3,
            duration=0,
            message="Linha 2: busy -> idle",
        ),
        GatewayEvent(
            id=4,
            created_at=datetime(2026, 7, 7, 9, 20, 0),
            event_type="congestion_end",
            busy_lines=3,
            idle_lines=1,
            duration=300,
            message="Fim de congestionamento",
        ),
    ]

    summary = build_report_summary(
        events,
        period="24h",
        now=datetime(2026, 7, 7, 10, 0, 0),
    )
    payload = report_summary_to_dict(summary)

    assert payload["congestion_seconds"] == 300
    assert payload["line_usage"][0]["line"] == 1
    assert payload["line_usage"][0]["sip"] == "3034"
    assert payload["line_usage"][0]["busy_seconds"] == 3600
