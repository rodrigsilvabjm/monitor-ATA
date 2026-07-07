from io import BytesIO

from fastapi import APIRouter
from fastapi import Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.gateway import Gateway
from app.models.gateway_event import GatewayEvent
from app.schemas.asterisk import AsteriskSnapshot
from app.schemas.gateway import GatewayCreate, GatewayResponse
from app.schemas.gateway_event import GatewayEventResponse
from app.schemas.gateway_line import GatewayLinesSnapshot
from app.schemas.status import StatusResponse
from app.services.monitoring import asterisk_ami_monitor, gateway_line_monitor
from app.services.reports import (
    build_events_excel,
    build_events_pdf,
    build_report_summary,
    normalize_period,
    report_summary_to_dict,
)
from app.services.status import build_status_response

router = APIRouter(tags=["api"])


@router.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return build_status_response()


@router.get("/lines", response_model=GatewayLinesSnapshot)
def get_gateway_lines() -> GatewayLinesSnapshot:
    return gateway_line_monitor.snapshot


@router.get("/gateways", response_model=list[GatewayResponse])
def list_gateways(db: Session = Depends(get_db)) -> list[Gateway]:
    return list(db.query(Gateway).order_by(Gateway.id).all())


@router.post("/gateways", response_model=GatewayResponse)
def create_gateway(payload: GatewayCreate, db: Session = Depends(get_db)) -> Gateway:
    gateway = Gateway(**payload.model_dump())
    db.add(gateway)
    db.commit()
    db.refresh(gateway)
    return gateway


@router.get("/asterisk", response_model=AsteriskSnapshot)
def get_asterisk_snapshot() -> AsteriskSnapshot:
    return asterisk_ami_monitor.snapshot


@router.get("/events", response_model=list[GatewayEventResponse])
def get_gateway_events(
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[GatewayEvent]:
    safe_limit = min(max(limit, 1), 500)
    return list(
        db.query(GatewayEvent)
        .order_by(desc(GatewayEvent.created_at))
        .limit(safe_limit)
        .all()
    )


@router.get("/reports/pdf")
def events_pdf_report(
    period: str = "24h",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    period_key = normalize_period(period)
    events = (
        db.query(GatewayEvent)
        .order_by(desc(GatewayEvent.created_at))
        .limit(5000)
        .all()
    )
    content = build_events_pdf(list(events), period_key)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=gateway-report-{period_key}.pdf"
            )
        },
    )


@router.get("/reports/excel")
def events_excel_report(
    period: str = "24h",
    db: Session = Depends(get_db),
) -> StreamingResponse:
    period_key = normalize_period(period)
    events = (
        db.query(GatewayEvent)
        .order_by(desc(GatewayEvent.created_at))
        .limit(5000)
        .all()
    )
    content = build_events_excel(list(events), period_key)
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename=gateway-report-{period_key}.xlsx"
            )
        },
    )


@router.get("/reports/summary")
def events_report_summary(
    period: str = "24h",
    db: Session = Depends(get_db),
) -> dict:
    period_key = normalize_period(period)
    events = (
        db.query(GatewayEvent)
        .order_by(desc(GatewayEvent.created_at))
        .limit(5000)
        .all()
    )
    summary = build_report_summary(list(events), period_key)
    return report_summary_to_dict(summary)


@router.get("/metrics")
def prometheus_metrics() -> Response:
    lines = gateway_line_monitor.snapshot.lines
    busy = sum(1 for line in lines if line.status == "busy")
    idle = sum(1 for line in lines if line.status == "idle")
    asterisk = asterisk_ami_monitor.snapshot
    content = "\n".join(
        [
            "# HELP gateway_monitor_busy_lines Busy gateway lines",
            "# TYPE gateway_monitor_busy_lines gauge",
            f"gateway_monitor_busy_lines {busy}",
            "# HELP gateway_monitor_idle_lines Idle gateway lines",
            "# TYPE gateway_monitor_idle_lines gauge",
            f"gateway_monitor_idle_lines {idle}",
            "# HELP gateway_monitor_asterisk_active_calls Active Asterisk calls",
            "# TYPE gateway_monitor_asterisk_active_calls gauge",
            f"gateway_monitor_asterisk_active_calls {asterisk.simultaneous_calls}",
            "# HELP gateway_monitor_asterisk_missed_calls Missed Asterisk calls",
            "# TYPE gateway_monitor_asterisk_missed_calls counter",
            f"gateway_monitor_asterisk_missed_calls {asterisk.missed_calls}",
            "",
        ]
    )
    return Response(content=content, media_type="text/plain; version=0.0.4")
