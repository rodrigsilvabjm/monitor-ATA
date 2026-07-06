import asyncio
import logging
import re
from datetime import UTC, datetime

from app.config import Settings
from app.schemas.asterisk import ActiveCall, AsteriskSnapshot

logger = logging.getLogger(__name__)

FXO_PATTERN = re.compile(r"(?:DAHDI|Zap|PJSIP|SIP)/(\d+)", re.IGNORECASE)


class AsteriskAmiMonitor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._active_calls: dict[str, ActiveCall] = {}
        self._completed_durations: list[int] = []
        self._missed_calls = 0
        self._snapshot = self._build_snapshot(connected=False)
        self._subscribers: set[asyncio.Queue[AsteriskSnapshot]] = set()
        self._task: asyncio.Task[None] | None = None

    @property
    def snapshot(self) -> AsteriskSnapshot:
        return self._snapshot

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def subscribe(self) -> asyncio.Queue[AsteriskSnapshot]:
        queue: asyncio.Queue[AsteriskSnapshot] = asyncio.Queue(maxsize=5)
        self._subscribers.add(queue)
        await queue.put(self._snapshot)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AsteriskSnapshot]) -> None:
        self._subscribers.discard(queue)

    async def _run_forever(self) -> None:
        while True:
            if not self._settings.asterisk_ami_enabled:
                self._snapshot = self._build_snapshot(connected=False)
                await self._broadcast()
                await asyncio.sleep(self._settings.asterisk_ami_reconnect_delay)
                continue

            try:
                await self._connect_and_read()
            except asyncio.CancelledError:
                raise
            except (TimeoutError, ConnectionError, OSError) as exc:
                logger.warning("Asterisk AMI unavailable: %s", exc)
                self._snapshot = self._build_snapshot(connected=False)
                await self._broadcast()
                await asyncio.sleep(self._settings.asterisk_ami_reconnect_delay)
            except Exception:
                logger.exception("Asterisk AMI connection failed")
                self._snapshot = self._build_snapshot(connected=False)
                await self._broadcast()
                await asyncio.sleep(self._settings.asterisk_ami_reconnect_delay)

    async def _connect_and_read(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                self._settings.asterisk_ami_host,
                self._settings.asterisk_ami_port,
            ),
            timeout=self._settings.asterisk_ami_timeout,
        )

        try:
            await asyncio.wait_for(
                reader.readline(),
                timeout=self._settings.asterisk_ami_timeout,
            )
            await self._login(writer)
            self._snapshot = self._build_snapshot(connected=True)
            await self._broadcast()

            while True:
                event = await read_ami_message(reader)
                if not event:
                    raise ConnectionError("Asterisk AMI connection closed")
                await self.process_event(event)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _login(self, writer: asyncio.StreamWriter) -> None:
        if not self._settings.asterisk_ami_username:
            raise ValueError("ASTERISK_AMI_USERNAME is required")
        if not self._settings.asterisk_ami_password:
            raise ValueError("ASTERISK_AMI_PASSWORD is required")

        payload = (
            "Action: Login\r\n"
            f"Username: {self._settings.asterisk_ami_username}\r\n"
            f"Secret: {self._settings.asterisk_ami_password}\r\n"
            "Events: on\r\n\r\n"
        )
        writer.write(payload.encode("utf-8"))
        await writer.drain()

    async def process_event(self, event: dict[str, str]) -> None:
        event_name = event.get("Event", "").lower()

        if event_name in {"newchannel", "dialbegin"}:
            self._upsert_call(event)
        elif event_name in {"bridgeenter", "dialend"}:
            self._mark_answered(event)
        elif event_name in {"hangup", "cdr"}:
            self._finish_call(event)
        else:
            return

        self._snapshot = self._build_snapshot(connected=True)
        await self._broadcast()

    def _upsert_call(self, event: dict[str, str]) -> None:
        unique_id = get_unique_id(event)
        if not unique_id:
            return

        now = datetime.now(UTC)
        call = self._active_calls.get(unique_id)
        if not call:
            call = ActiveCall(unique_id=unique_id, started_at=now)

        call.source_number = first_present(
            call.source_number,
            event.get("CallerIDNum"),
            event.get("ConnectedLineNum"),
            event.get("Source"),
        )
        call.destination_number = first_present(
            call.destination_number,
            event.get("Exten"),
            event.get("DestCallerIDNum"),
            event.get("Destination"),
            event.get("DestExten"),
        )
        call.fxo_line = first_present(
            call.fxo_line,
            extract_fxo_line(event.get("Channel")),
            extract_fxo_line(event.get("DestChannel")),
        )
        self._active_calls[unique_id] = call

    def _mark_answered(self, event: dict[str, str]) -> None:
        unique_id = get_unique_id(event)
        if not unique_id or unique_id not in self._active_calls:
            return

        call = self._active_calls[unique_id]
        call.status = "answered"
        call.answered_at = call.answered_at or datetime.now(UTC)
        call.answered_extension = first_present(
            call.answered_extension,
            event.get("ConnectedLineNum"),
            event.get("DestConnectedLineNum"),
            event.get("Exten"),
            extract_extension(event.get("DestChannel")),
        )
        call.fxo_line = first_present(
            call.fxo_line,
            extract_fxo_line(event.get("Channel")),
            extract_fxo_line(event.get("DestChannel")),
        )

    def _finish_call(self, event: dict[str, str]) -> None:
        unique_id = get_unique_id(event)
        if not unique_id:
            return

        call = self._active_calls.pop(unique_id, None)
        duration = parse_duration(event) or (
            int((datetime.now(UTC) - call.started_at).total_seconds())
            if call
            else 0
        )

        if duration > 0:
            self._completed_durations.append(duration)
            self._completed_durations = self._completed_durations[-500:]

        disposition = event.get("Disposition", "").lower()
        cause = event.get("Cause-txt", "").lower()
        if call and call.answered_at is None and (
            duration == 0 or "no answer" in disposition or "normal clearing" not in cause
        ):
            self._missed_calls += 1

    def _build_snapshot(self, connected: bool) -> AsteriskSnapshot:
        now = datetime.now(UTC)
        active_calls = []
        for call in self._active_calls.values():
            call.duration_seconds = int((now - call.started_at).total_seconds())
            active_calls.append(call)

        average_duration = (
            int(sum(self._completed_durations) / len(self._completed_durations))
            if self._completed_durations
            else 0
        )

        return AsteriskSnapshot(
            connected=connected,
            updated_at=now,
            active_calls=sorted(active_calls, key=lambda item: item.started_at),
            simultaneous_calls=len(active_calls),
            average_duration_seconds=average_duration,
            missed_calls=self._missed_calls,
        )

    async def _broadcast(self) -> None:
        stale_queues: list[asyncio.Queue[AsteriskSnapshot]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(self._snapshot)
            except asyncio.QueueFull:
                stale_queues.append(queue)

        for queue in stale_queues:
            self._subscribers.discard(queue)


async def read_ami_message(reader: asyncio.StreamReader) -> dict[str, str]:
    lines: list[str] = []
    while True:
        raw_line = await reader.readline()
        if not raw_line:
            return {}
        line = raw_line.decode("utf-8", errors="ignore").strip()
        if not line:
            break
        lines.append(line)
    return parse_ami_message(lines)


def parse_ami_message(lines: list[str]) -> dict[str, str]:
    message: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        message[key.strip()] = value.strip()
    return message


def get_unique_id(event: dict[str, str]) -> str | None:
    return first_present(
        event.get("Uniqueid"),
        event.get("UniqueID"),
        event.get("Linkedid"),
        event.get("DestUniqueid"),
    )


def first_present(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def extract_fxo_line(channel: str | None) -> str | None:
    if not channel:
        return None
    match = FXO_PATTERN.search(channel)
    if not match:
        return None
    return match.group(1)


def extract_extension(channel: str | None) -> str | None:
    if not channel or "/" not in channel:
        return None
    return channel.split("/", maxsplit=1)[1].split("-", maxsplit=1)[0]


def parse_duration(event: dict[str, str]) -> int | None:
    for key in ("Duration", "BillableSeconds", "Billsec"):
        value = event.get(key)
        if value and value.isdigit():
            return int(value)
    return None
