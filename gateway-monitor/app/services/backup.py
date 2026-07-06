import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models.gateway_event import GatewayEvent

logger = logging.getLogger(__name__)


class EventBackupService:
    def __init__(self, settings: Settings, session_factory: sessionmaker) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if not self._settings.backup_enabled:
            return
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

    async def _run_forever(self) -> None:
        while True:
            try:
                self.create_backup()
            except Exception:
                logger.exception("Failed to create automatic backup")
            await asyncio.sleep(self._settings.backup_interval_minutes * 60)

    def create_backup(self) -> Path:
        backup_dir = Path(self._settings.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now(UTC).strftime("gateway-events-%Y%m%d-%H%M%S.json")
        backup_path = backup_dir / filename

        with self._session_factory() as session:
            events = session.query(GatewayEvent).order_by(GatewayEvent.id).all()

        payload = [
            {
                "id": event.id,
                "created_at": event.created_at.isoformat(),
                "event_type": event.event_type,
                "busy_lines": event.busy_lines,
                "idle_lines": event.idle_lines,
                "duration": event.duration,
                "message": event.message,
            }
            for event in events
        ]
        backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return backup_path
