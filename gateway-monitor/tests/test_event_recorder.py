from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.gateway_event import GatewayEvent
from app.schemas.gateway_line import GatewayLineState, GatewayLinesSnapshot
from app.services.event_recorder import GatewayEventRecorder


class FakeTelegramNotifier:
    def __init__(self) -> None:
        self.started_at: list[datetime] = []
        self.ended_durations: list[int] = []

    def send_congestion_started(self, event_time: datetime) -> None:
        self.started_at.append(event_time)

    def send_congestion_ended(self, duration_seconds: int) -> None:
        self.ended_durations.append(duration_seconds)


def _session_factory() -> sessionmaker:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _snapshot(statuses: list[str], updated_at: datetime) -> GatewayLinesSnapshot:
    return GatewayLinesSnapshot(
        gateway_host="127.0.0.1",
        connected=True,
        updated_at=updated_at,
        lines=[
            GatewayLineState(
                line=index,
                label=f"Linha {index}",
                status=status,
            )
            for index, status in enumerate(statuses, start=1)
        ],
    )


def test_recorder_persists_state_changes() -> None:
    session_factory = _session_factory()
    recorder = GatewayEventRecorder(session_factory)
    now = datetime.now(UTC)

    recorder.process_snapshot(_snapshot(["idle"] * 8, now))
    recorder.process_snapshot(_snapshot(["busy"] + ["idle"] * 7, now))

    with session_factory() as session:
        events = session.query(GatewayEvent).all()

    assert len(events) == 1
    assert events[0].event_type == "state_change"
    assert events[0].busy_lines == 1
    assert events[0].idle_lines == 7


def test_recorder_persists_congestion_duration() -> None:
    session_factory = _session_factory()
    notifier = FakeTelegramNotifier()
    recorder = GatewayEventRecorder(session_factory, telegram_notifier=notifier)
    now = datetime.now(UTC)

    recorder.process_snapshot(_snapshot(["idle"] * 8, now))
    recorder.process_snapshot(_snapshot(["busy"] * 8, now + timedelta(seconds=2)))
    recorder.process_snapshot(
        _snapshot(["idle"] + ["busy"] * 7, now + timedelta(seconds=12))
    )

    with session_factory() as session:
        events = (
            session.query(GatewayEvent)
            .order_by(GatewayEvent.id)
            .all()
        )

    assert [event.event_type for event in events] == [
        "state_change",
        "congestion_start",
        "state_change",
        "congestion_end",
    ]
    assert events[-1].duration == 10
    assert notifier.started_at == [now + timedelta(seconds=2)]
    assert notifier.ended_durations == [10]


def test_recorder_detects_congestion_with_four_monitored_lines() -> None:
    session_factory = _session_factory()
    recorder = GatewayEventRecorder(session_factory)
    now = datetime.now(UTC)

    recorder.process_snapshot(_snapshot(["idle"] * 4, now))
    recorder.process_snapshot(_snapshot(["busy"] * 4, now + timedelta(seconds=1)))

    with session_factory() as session:
        events = (
            session.query(GatewayEvent)
            .order_by(GatewayEvent.id)
            .all()
        )

    assert events[-1].event_type == "congestion_start"
    assert events[-1].busy_lines == 4
    assert events[-1].idle_lines == 0
