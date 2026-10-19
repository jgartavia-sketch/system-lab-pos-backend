from datetime import datetime
from pydantic import BaseModel, ConfigDict

class AdminStoriesReader(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    phone: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

class AdminStoriesReadersPage(BaseModel):
    total: int
    filtered_total: int
    items: list[AdminStoriesReader]
