from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GatewayCreate(BaseModel):
    name: str
    host: str
    snmp_community: str = "public"
    enabled: bool = True


class GatewayResponse(BaseModel):
    id: int
    name: str
    host: str
    snmp_community: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
