from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

class ClientEventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=500)
    event_date: date

class ClientEventResponse(ClientEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    created_at: datetime
    updated_at: datetime
