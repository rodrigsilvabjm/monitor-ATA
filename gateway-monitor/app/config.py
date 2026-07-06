from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = Field(default="Gateway Monitor", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    timezone: str = Field(default="America/Sao_Paulo", alias="APP_TIMEZONE")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")

    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD")
    session_cookie_name: str = Field(
        default="gateway_monitor_session",
        alias="SESSION_COOKIE_NAME",
    )
    session_duration_minutes: int = Field(
        default=480,
        alias="SESSION_DURATION_MINUTES",
    )

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: Path = Field(default=Path("logs/application.log"), alias="LOG_FILE")

    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_timeout: float = Field(default=5.0, alias="TELEGRAM_TIMEOUT")

    asterisk_ami_enabled: bool = Field(default=False, alias="ASTERISK_AMI_ENABLED")
    asterisk_ami_host: str = Field(default="127.0.0.1", alias="ASTERISK_AMI_HOST")
    asterisk_ami_port: int = Field(default=5038, alias="ASTERISK_AMI_PORT")
    asterisk_ami_username: str | None = Field(
        default=None,
        alias="ASTERISK_AMI_USERNAME",
    )
    asterisk_ami_password: str | None = Field(
        default=None,
        alias="ASTERISK_AMI_PASSWORD",
    )
    asterisk_ami_timeout: float = Field(default=5.0, alias="ASTERISK_AMI_TIMEOUT")
    asterisk_ami_reconnect_delay: float = Field(
        default=5.0,
        alias="ASTERISK_AMI_RECONNECT_DELAY",
    )

    backup_enabled: bool = Field(default=False, alias="BACKUP_ENABLED")
    backup_interval_minutes: int = Field(default=60, alias="BACKUP_INTERVAL_MINUTES")
    backup_dir: Path = Field(default=Path("backups"), alias="BACKUP_DIR")

    grafana_url: str | None = Field(default=None, alias="GRAFANA_URL")
    whatsapp_enabled: bool = Field(default=False, alias="WHATSAPP_ENABLED")
    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")

    snmp_enabled: bool = Field(default=True, alias="SNMP_ENABLED")
    snmp_host: str = Field(default="192.168.0.1", alias="SNMP_HOST")
    snmp_port: int = Field(default=161, alias="SNMP_PORT")
    snmp_community: str = Field(default="public", alias="SNMP_COMMUNITY")
    snmp_version: str = Field(default="2c", alias="SNMP_VERSION")
    snmp_timeout: float = Field(default=1.0, alias="SNMP_TIMEOUT")
    snmp_retries: int = Field(default=0, alias="SNMP_RETRIES")
    snmp_poll_interval: float = Field(default=1.0, alias="SNMP_POLL_INTERVAL")
    snmp_mib_dir: Path = Field(default=Path("app/mibs"), alias="SNMP_MIB_DIR")
    snmp_mib_name: str | None = Field(default=None, alias="SNMP_MIB_NAME")
    gateway_monitored_lines: str = Field(
        default="1,2,3,4,5,6,7,8",
        alias="GATEWAY_MONITORED_LINES",
    )

    snmp_line_1_oid: str | None = Field(default=None, alias="SNMP_LINE_1_OID")
    snmp_line_2_oid: str | None = Field(default=None, alias="SNMP_LINE_2_OID")
    snmp_line_3_oid: str | None = Field(default=None, alias="SNMP_LINE_3_OID")
    snmp_line_4_oid: str | None = Field(default=None, alias="SNMP_LINE_4_OID")
    snmp_line_5_oid: str | None = Field(default=None, alias="SNMP_LINE_5_OID")
    snmp_line_6_oid: str | None = Field(default=None, alias="SNMP_LINE_6_OID")
    snmp_line_7_oid: str | None = Field(default=None, alias="SNMP_LINE_7_OID")
    snmp_line_8_oid: str | None = Field(default=None, alias="SNMP_LINE_8_OID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    @property
    def database_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def snmp_line_oids(self) -> dict[int, str]:
        configured_oids = {
            1: self.snmp_line_1_oid,
            2: self.snmp_line_2_oid,
            3: self.snmp_line_3_oid,
            4: self.snmp_line_4_oid,
            5: self.snmp_line_5_oid,
            6: self.snmp_line_6_oid,
            7: self.snmp_line_7_oid,
            8: self.snmp_line_8_oid,
        }
        return {
            line_number: oid
            for line_number, oid in configured_oids.items()
            if oid and line_number in self.monitored_line_numbers
        }

    @property
    def monitored_line_numbers(self) -> list[int]:
        line_numbers: list[int] = []
        for value in self.gateway_monitored_lines.split(","):
            value = value.strip()
            if value.isdigit():
                line_number = int(value)
                if 1 <= line_number <= 8:
                    line_numbers.append(line_number)
        return line_numbers or [1, 2, 3, 4]


@lru_cache
def get_settings() -> Settings:
    return Settings()
