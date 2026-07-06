from datetime import datetime

from pydantic import BaseModel


class GatewayLineState(BaseModel):
    line: int
    label: str
    status: str
    raw_value: str | None = None
    message: str | None = None


class GatewayLinesSnapshot(BaseModel):
    gateway_host: str
    connected: bool
    updated_at: datetime
    lines: list[GatewayLineState]
