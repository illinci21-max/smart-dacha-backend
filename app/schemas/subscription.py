from pydantic import BaseModel, field_validator
from typing import Literal


class CheckoutRequest(BaseModel):
    tier: Literal["premium", "premium_plus"]
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    success_url: str
    cancel_url: str

    # FIX: Валідація URL — не допускаємо порожні рядки
    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("http"):
            raise ValueError("URL має починатися з http/https")
        return v


class SubscriptionResponse(BaseModel):
    tier: str
    is_active: bool
    expires_at: str | None
    limits: dict
    features: list[str]
