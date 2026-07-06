import logging
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from app.models.gateway_event import GatewayEvent
from app.schemas.gateway_line import GatewayLinesSnapshot
from app.services.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class GatewayEventRecorder:
    def __init__(
        self,
        session_factory: sessionmaker,
        telegram_notifier: TelegramNotifier | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._telegram_notifier = telegram_notifier
        self._last_status_by_line: dict[int, str] = {}
        self._congestion_started_at: datetime | None = None

    def process_snapshot(self, snapshot: GatewayLinesSnapshot) -> None:
        if not snapshot.connected:
            return

        changes = self._detect_line_changes(snapshot)
        busy_lines = count_busy_lines(snapshot)
        idle_lines = count_idle_lines(snapshot)

        if changes:
            self._create_event(
                event_type="state_change",
                busy_lines=busy_lines,
                idle_lines=idle_lines,
                duration=0,
                message="; ".join(changes),
            )

        self._process_congestion(snapshot, busy_lines, idle_lines)

    def _detect_line_changes(self, snapshot: GatewayLinesSnapshot) -> list[str]:
        changes: list[str] = []
        current_status_by_line = {
            line.line: line.status
            for line in snapshot.lines
            if line.status not in {"unknown", "not_configured", "configured"}
        }

        for line_number, current_status in current_status_by_line.items():
            previous_status = self._last_status_by_line.get(line_number)
            if previous_status is None:
                continue
            if previous_status != current_status:
                changes.append(
                    f"Linha {line_number}: {previous_status} -> {current_status}"
                )

        self._last_status_by_line = current_status_by_line
        return changes

    def _process_congestion(
        self,
        snapshot: GatewayLinesSnapshot,
        busy_lines: int,
        idle_lines: int,
    ) -> None:
        has_congestion = busy_lines == len(snapshot.lines) and busy_lines > 0

        if has_congestion and self._congestion_started_at is None:
            self._congestion_started_at = snapshot.updated_at
            self._create_event(
                event_type="congestion_start",
                busy_lines=busy_lines,
                idle_lines=idle_lines,
                duration=0,
                message="Inicio de congestionamento: todas as linhas ocupadas",
            )
            if self._telegram_notifier:
                self._telegram_notifier.send_congestion_started(snapshot.updated_at)
            return

        if not has_congestion and self._congestion_started_at is not None:
            duration = int(
                (snapshot.updated_at - self._congestion_started_at).total_seconds()
            )
            self._create_event(
                event_type="congestion_end",
                busy_lines=busy_lines,
                idle_lines=idle_lines,
                duration=max(duration, 0),
                message="Fim de congestionamento",
            )
            if self._telegram_notifier:
                self._telegram_notifier.send_congestion_ended(max(duration, 0))
            self._congestion_started_at = None

    def _create_event(
        self,
        event_type: str,
        busy_lines: int,
        idle_lines: int,
        duration: int,
        message: str,
    ) -> None:
        try:
            with self._session_factory() as session:
                session.add(
                    GatewayEvent(
                        event_type=event_type,
                        busy_lines=busy_lines,
                        idle_lines=idle_lines,
                        duration=duration,
                        message=message,
                    )
                )
                session.commit()
        except Exception:
            logger.exception("Failed to persist gateway event")


def count_busy_lines(snapshot: GatewayLinesSnapshot) -> int:
    return sum(1 for line in snapshot.lines if line.status == "busy")


def count_idle_lines(snapshot: GatewayLinesSnapshot) -> int:
    return sum(1 for line in snapshot.lines if line.status == "idle")
