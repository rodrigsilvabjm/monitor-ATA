import csv
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import Settings

logger = logging.getLogger(__name__)

REVERSE_READ_BLOCK_SIZE = 1024 * 1024

MASTER_CSV_FIELDS = [
    "accountcode",
    "src",
    "dst",
    "dcontext",
    "clid",
    "channel",
    "dstchannel",
    "lastapp",
    "lastdata",
    "start",
    "answer",
    "end",
    "duration",
    "billsec",
    "disposition",
    "amaflags",
    "uniqueid",
    "userfield",
    "sequence",
]


@dataclass(frozen=True)
class CdrRecord:
    src: str
    dst: str
    channel: str
    dstchannel: str
    lastapp: str
    lastdata: str
    start: datetime
    answer: datetime | None
    end: datetime
    duration: int
    billsec: int
    disposition: str
    uniqueid: str
    userfield: str = ""


class AsteriskCdrReader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def read_records(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[CdrRecord]:
        source = self._settings.asterisk_cdr_source.strip().lower()
        if source in {"csv", "master_csv", "file"}:
            return self._read_csv(self._settings.asterisk_cdr_csv_path, started_at, ended_at)
        if source == "sqlite":
            return self._read_sqlite(started_at, ended_at)
        if source in {"mysql", "mariadb"}:
            return self._read_mysql(started_at, ended_at)
        return []

    def _read_csv(
        self,
        path: Path,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[CdrRecord]:
        if not path.exists():
            return []

        records: list[CdrRecord] = []
        try:
            for line in iter_file_lines_reverse(path):
                record = cdr_from_csv_line(line)
                if not record:
                    continue
                if record.start < started_at:
                    break
                if record.start <= ended_at:
                    records.append(record)
        except OSError as exc:
            logger.warning("Unable to read Asterisk CDR CSV %s: %s", path, exc)
            return []
        records.reverse()
        return records

    def _read_sqlite(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[CdrRecord]:
        if not self._settings.asterisk_cdr_sqlite_path:
            return []
        if not self._settings.asterisk_cdr_sqlite_path.exists():
            return []

        with sqlite3.connect(self._settings.asterisk_cdr_sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT * FROM {self._settings.asterisk_cdr_table}
                WHERE datetime(start) BETWEEN datetime(?) AND datetime(?)
                ORDER BY datetime(start)
                """,
                (started_at.isoformat(sep=" "), ended_at.isoformat(sep=" ")),
            ).fetchall()
        return [record for row in rows if (record := cdr_from_mapping(dict(row)))]

    def _read_mysql(
        self,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[CdrRecord]:
        try:
            import pymysql
        except ImportError:
            return []

        if not self._settings.asterisk_cdr_mysql_database:
            return []
        if not self._settings.asterisk_cdr_mysql_user:
            return []

        connection = pymysql.connect(
            host=self._settings.asterisk_cdr_mysql_host,
            port=self._settings.asterisk_cdr_mysql_port,
            user=self._settings.asterisk_cdr_mysql_user,
            password=self._settings.asterisk_cdr_mysql_password or "",
            database=self._settings.asterisk_cdr_mysql_database,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT * FROM {self._settings.asterisk_cdr_table}
                    WHERE start BETWEEN %s AND %s
                    ORDER BY start
                    """,
                    (started_at, ended_at),
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
        return [record for row in rows if (record := cdr_from_mapping(row))]


def cdr_from_csv_row(row: list[str]) -> CdrRecord | None:
    if len(row) < 18:
        return None
    values = {field: row[index] if index < len(row) else "" for index, field in enumerate(MASTER_CSV_FIELDS)}
    return cdr_from_mapping(values)


def cdr_from_csv_line(line: str) -> CdrRecord | None:
    try:
        row = next(csv.reader([line]))
    except csv.Error:
        return None
    return cdr_from_csv_row(row)


def cdr_from_mapping(values: dict[str, Any]) -> CdrRecord | None:
    start = parse_datetime(values.get("start"))
    end = parse_datetime(values.get("end"))
    if not start or not end:
        return None

    return CdrRecord(
        src=str(values.get("src") or ""),
        dst=str(values.get("dst") or ""),
        channel=str(values.get("channel") or ""),
        dstchannel=str(values.get("dstchannel") or ""),
        lastapp=str(values.get("lastapp") or ""),
        lastdata=str(values.get("lastdata") or ""),
        start=start,
        answer=parse_datetime(values.get("answer")),
        end=end,
        duration=parse_int(values.get("duration")),
        billsec=parse_int(values.get("billsec")),
        disposition=str(values.get("disposition") or "").upper(),
        uniqueid=str(values.get("uniqueid") or ""),
        userfield=str(values.get("userfield") or ""),
    )


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def parse_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def iter_file_lines_reverse(path: Path) -> Iterator[str]:
    with path.open("rb") as file:
        file.seek(0, 2)
        position = file.tell()
        pending = b""

        while position > 0:
            read_size = min(REVERSE_READ_BLOCK_SIZE, position)
            position -= read_size
            file.seek(position)
            block = file.read(read_size) + pending
            lines = block.splitlines()

            if position > 0:
                pending = lines[0] if lines else b""
                lines = lines[1:]
            else:
                pending = b""

            for line in reversed(lines):
                decoded = line.decode("utf-8", errors="ignore").strip()
                if decoded:
                    yield decoded

        if pending:
            decoded = pending.decode("utf-8", errors="ignore").strip()
            if decoded:
                yield decoded
