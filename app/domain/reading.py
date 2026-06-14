from datetime import datetime

from pydantic import BaseModel


class SensorReading(BaseModel):
    tenant_id: str
    sensor_id: str
    room: str
    type: str
    value: float
    unit: str
    timestamp: datetime