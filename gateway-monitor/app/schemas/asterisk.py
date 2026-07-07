from datetime import datetime

from pydantic import BaseModel


class ActiveCall(BaseModel):
    unique_id: str
    linked_id: str | None = None
    source_number: str | None = None
    destination_number: str | None = None
    answered_extension: str | None = None
    fxo_line: str | None = None
    started_at: datetime
    answered_at: datetime | None = None
    duration_seconds: int = 0
    status: str = "ringing"


class AsteriskSnapshot(BaseModel):
    connected: bool
    updated_at: datetime
    active_calls: list[ActiveCall]
    simultaneous_calls: int
    average_duration_seconds: int
    missed_calls: int
