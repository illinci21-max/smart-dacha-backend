import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    subscription_tier: str
    subscription_expires_at: datetime | None
    plots_limit: int
    plants_limit: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    fcm_token: str | None = None
