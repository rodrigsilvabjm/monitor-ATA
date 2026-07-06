from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GatewayEventResponse(BaseModel):
    id: int
    created_at: datetime
    busy_lines: int
    idle_lines: int
    event_type: str
    duration: int
    message: str

    model_config = ConfigDict(from_attributes=True)
