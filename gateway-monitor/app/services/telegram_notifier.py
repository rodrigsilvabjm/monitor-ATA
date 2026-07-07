import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(
            self._settings.telegram_enabled
            and self._settings.telegram_bot_token
            and self._settings.telegram_chat_id
        )

    def send_congestion_started(self, event_time: datetime) -> None:
        message = build_congestion_started_message(
            event_time,
            self._settings.timezone,
        )
        self._send_message(message)

    def send_congestion_ended(self, duration_seconds: int) -> None:
        message = build_congestion_ended_message(duration_seconds)
        self._send_message(message)

    def _send_message(self, message: str) -> None:
        if not self.is_configured:
            logger.info("Telegram alert skipped: integration is not configured")
            return

        url = (
            "https://api.telegram.org/bot"
            f"{self._settings.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": self._settings.telegram_chat_id,
            "text": message,
        }

        try:
            with httpx.Client(timeout=self._settings.telegram_timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except Exception:
            logger.exception("Failed to send Telegram alert")


def build_congestion_started_message(
    event_time: datetime,
    timezone: str,
) -> str:
    local_time = event_time.astimezone(ZoneInfo(timezone))
    return (
        "\U0001F6A8 Gateway Monitor\n\n"
        "Todas as linhas est\u00e3o ocupadas.\n\n"
        "Data:\n"
        f"{local_time.strftime('%d/%m/%Y')}\n\n"
        "Hora:\n"
        f"{local_time.strftime('%H:%M:%S')}"
    )


def build_congestion_ended_message(duration_seconds: int) -> str:
    return (
        "\u2705 Congestionamento encerrado\n\n"
        "Dura\u00e7\u00e3o\n\n"
        f"{format_duration_pt_br(duration_seconds)}"
    )


def format_duration_pt_br(duration_seconds: int) -> str:
    safe_seconds = max(duration_seconds, 0)
    minutes, seconds = divmod(safe_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours} {'hora' if hours == 1 else 'horas'}")
    if minutes:
        parts.append(f"{minutes} {'minuto' if minutes == 1 else 'minutos'}")
    if seconds or not parts:
        parts.append(f"{seconds} {'segundo' if seconds == 1 else 'segundos'}")

    if len(parts) == 1:
        return parts[0]
    return " e ".join(parts)
