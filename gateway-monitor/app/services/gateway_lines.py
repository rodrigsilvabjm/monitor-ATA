import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.config import Settings
from app.schemas.gateway_line import GatewayLineState, GatewayLinesSnapshot
from app.services.snmp_client import PySnmpClient, SnmpClient

if TYPE_CHECKING:
    from app.services.event_recorder import GatewayEventRecorder

logger = logging.getLogger(__name__)


class GatewayLineMonitor:
    def __init__(
        self,
        settings: Settings,
        snmp_client: SnmpClient | None = None,
        event_recorder: "GatewayEventRecorder | None" = None,
        active_line_provider: Callable[[], tuple[set[int], bool]] | None = None,
    ) -> None:
        self._settings = settings
        self._snmp_client = snmp_client or PySnmpClient(settings)
        self._event_recorder = event_recorder
        self._active_line_provider = active_line_provider
        self._snapshot = self._build_initial_snapshot()
        self._subscribers: set[asyncio.Queue[GatewayLinesSnapshot]] = set()
        self._task: asyncio.Task[None] | None = None

    @property
    def snapshot(self) -> GatewayLinesSnapshot:
        return self._snapshot

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._poll_forever())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def subscribe(self) -> asyncio.Queue[GatewayLinesSnapshot]:
        queue: asyncio.Queue[GatewayLinesSnapshot] = asyncio.Queue(maxsize=5)
        self._subscribers.add(queue)
        await queue.put(self._snapshot)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[GatewayLinesSnapshot]) -> None:
        self._subscribers.discard(queue)

    async def refresh_once(self) -> GatewayLinesSnapshot:
        monitored_lines = self._settings.monitored_line_numbers
        if (
            self._settings.use_asterisk_line_status
            and self._active_line_provider
        ):
            active_lines, connected = self._active_line_provider()
            self._snapshot = self._build_specific_busy_lines_snapshot(
                monitored_lines=monitored_lines,
                active_lines=active_lines,
                connected=connected,
                message="Fonte: Asterisk AMI",
            )
            if self._event_recorder:
                self._event_recorder.process_snapshot(self._snapshot)
            await self._broadcast(self._snapshot)
            return self._snapshot

        if not self._settings.snmp_enabled:
            self._snapshot = self._build_disabled_snapshot()
            await self._broadcast(self._snapshot)
            return self._snapshot

        if self._settings.busy_lines_oids:
            self._snapshot = await self._read_aggregate_busy_lines(monitored_lines)
            if self._event_recorder:
                self._event_recorder.process_snapshot(self._snapshot)
            await self._broadcast(self._snapshot)
            return self._snapshot

        line_oids = self._settings.snmp_line_oids
        if any(line_number not in line_oids for line_number in monitored_lines):
            self._snapshot = self._build_configuration_snapshot(line_oids)
            await self._broadcast(self._snapshot)
            return self._snapshot

        line_states = await asyncio.gather(
            *[
                self._read_line(line_number, oid)
                for line_number, oid in sorted(line_oids.items())
                if line_number in monitored_lines
            ]
        )
        connected = all(line.message is None for line in line_states)
        self._snapshot = GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=connected,
            updated_at=datetime.now(UTC),
            lines=list(line_states),
        )
        if self._event_recorder:
            self._event_recorder.process_snapshot(self._snapshot)
        await self._broadcast(self._snapshot)
        return self._snapshot

    async def _poll_forever(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except Exception:
                logger.exception("Unexpected failure while polling SNMP gateway")
            await asyncio.sleep(self._settings.snmp_poll_interval)

    async def _read_line(self, line_number: int, oid: str) -> GatewayLineState:
        result = await self._snmp_client.get_value(oid)
        status = normalize_line_status(result.value)
        return GatewayLineState(
            line=line_number,
            label=f"Linha {line_number}",
            status=status,
            raw_value=result.value,
            message=result.error,
        )

    async def _read_aggregate_busy_lines(
        self,
        monitored_lines: list[int],
    ) -> GatewayLinesSnapshot:
        results = await asyncio.gather(
            *[
                self._snmp_client.get_value(oid)
                for oid in self._settings.busy_lines_oids
            ]
        )
        errors = [result.error for result in results if result.error]
        busy_count = sum(parse_busy_count(result.value) for result in results)
        return self._build_busy_count_snapshot(
            monitored_lines=monitored_lines,
            busy_count=busy_count,
            connected=not errors,
            raw_value=str(busy_count),
            message="; ".join(errors) if errors else None,
        )

    def _build_busy_count_snapshot(
        self,
        monitored_lines: list[int],
        busy_count: int,
        connected: bool,
        raw_value: str,
        message: str | None,
    ) -> GatewayLinesSnapshot:
        safe_busy_count = max(0, min(busy_count, len(monitored_lines)))
        return GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=connected,
            updated_at=datetime.now(UTC),
            lines=[
                GatewayLineState(
                    line=line_number,
                    label=f"Linha {line_number}",
                    status="busy" if index < safe_busy_count else "idle",
                    raw_value=raw_value,
                    message=message,
                )
                for index, line_number in enumerate(monitored_lines)
            ],
        )

    def _build_specific_busy_lines_snapshot(
        self,
        monitored_lines: list[int],
        active_lines: set[int],
        connected: bool,
        message: str | None,
    ) -> GatewayLinesSnapshot:
        monitored = set(monitored_lines)
        safe_active_lines = active_lines.intersection(monitored)
        raw_value = ",".join(str(line) for line in sorted(safe_active_lines)) or "0"
        return GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=connected,
            updated_at=datetime.now(UTC),
            lines=[
                GatewayLineState(
                    line=line_number,
                    label=f"Linha {line_number}",
                    status="busy" if line_number in safe_active_lines else "idle",
                    raw_value=raw_value,
                    message=message,
                )
                for line_number in monitored_lines
            ],
        )

    async def _broadcast(self, snapshot: GatewayLinesSnapshot) -> None:
        stale_queues: list[asyncio.Queue[GatewayLinesSnapshot]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                stale_queues.append(queue)

        for queue in stale_queues:
            self._subscribers.discard(queue)

    def _build_initial_snapshot(self) -> GatewayLinesSnapshot:
        return GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=False,
            updated_at=datetime.now(UTC),
            lines=[
                GatewayLineState(
                    line=line_number,
                    label=f"Linha {line_number}",
                    status="unknown",
                    message="Aguardando primeira leitura SNMP",
                )
                for line_number in self._settings.monitored_line_numbers
            ],
        )

    def _build_disabled_snapshot(self) -> GatewayLinesSnapshot:
        return GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=False,
            updated_at=datetime.now(UTC),
            lines=[
                GatewayLineState(
                    line=line_number,
                    label=f"Linha {line_number}",
                    status="disabled",
                    message="SNMP desabilitado por configuracao",
                )
                for line_number in self._settings.monitored_line_numbers
            ],
        )

    def _build_configuration_snapshot(
        self,
        line_oids: dict[int, str],
    ) -> GatewayLinesSnapshot:
        return GatewayLinesSnapshot(
            gateway_host=self._settings.snmp_host,
            connected=False,
            updated_at=datetime.now(UTC),
            lines=[
                GatewayLineState(
                    line=line_number,
                    label=f"Linha {line_number}",
                    status="not_configured"
                    if line_number not in line_oids
                    else "configured",
                    message="Configure o OID da linha no .env",
                )
                for line_number in self._settings.monitored_line_numbers
            ],
        )


def normalize_line_status(raw_value: str | None) -> str:
    if raw_value is None:
        return "unknown"

    normalized = raw_value.strip().lower()
    status_map = {
        "0": "idle",
        "1": "busy",
        "2": "ringing",
        "3": "unavailable",
        "idle": "idle",
        "free": "idle",
        "onhook": "idle",
        "busy": "busy",
        "active": "busy",
        "offhook": "busy",
        "ringing": "ringing",
        "ring": "ringing",
        "unavailable": "unavailable",
        "down": "unavailable",
        "offline": "unavailable",
    }
    if normalized in status_map:
        return status_map[normalized]
    if normalized.isdigit():
        return "busy" if int(normalized) > 0 else "idle"
    return "unknown"


def parse_busy_count(raw_value: str | None) -> int:
    if raw_value is None:
        return 0
    normalized = raw_value.strip()
    if normalized.startswith("-"):
        return 0
    if normalized.isdigit():
        return int(normalized)
    return 0
