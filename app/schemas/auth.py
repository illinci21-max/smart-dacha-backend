from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Пароль має бути не менше 8 символів")
        # FIX: мінімальна вимога складності паролю
        if v.isdigit() or v.isalpha():
            raise ValueError("Пароль має містити літери та цифри")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    # FIX: UUID замість str для id
    id: UUID
    email: str
    full_name: str | None
    subscription_tier: str
    subscription_expires_at: datetime | None
    plots_limit: int
    plants_limit: int
    created_at: datetime

    model_config = {"from_attributes": True}
