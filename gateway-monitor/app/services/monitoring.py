from app.config import get_settings
from app.database import SessionLocal
from app.services.asterisk_ami import AsteriskAmiMonitor
from app.services.backup import EventBackupService
from app.services.event_recorder import GatewayEventRecorder
from app.services.gateway_lines import GatewayLineMonitor
from app.services.telegram_notifier import TelegramNotifier

settings = get_settings()
telegram_notifier = TelegramNotifier(settings)
gateway_event_recorder = GatewayEventRecorder(
    SessionLocal,
    telegram_notifier=telegram_notifier,
)
gateway_line_monitor = GatewayLineMonitor(
    settings,
    event_recorder=gateway_event_recorder,
)
asterisk_ami_monitor = AsteriskAmiMonitor(settings)
event_backup_service = EventBackupService(settings, SessionLocal)
