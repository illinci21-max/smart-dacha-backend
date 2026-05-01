"""Finance schemas — request/response models for the finance API."""
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, UUID4


class FinanceTransactionCreate(BaseModel):
    type: Literal["income", "expense"]
    amount: float = Field(gt=0)
    plot: str | None = None
    category: str | None = None
    note: str | None = None
    date: datetime | None = None  # if None, server uses now()


class FinanceTransactionUpdate(BaseModel):
    type: Literal["income", "expense"] | None = None
    amount: float | None = Field(default=None, gt=0)
    plot: str | None = None
    category: str | None = None
    note: str | None = None
    date: datetime | None = None


class FinanceTransactionResponse(BaseModel):
    id: UUID4
    type: str
    amount: float
    plot: str | None = None
    category: str | None = None
    note: str | None = None
    date: datetime
    created_at: datetime


class FinanceStatsResponse(BaseModel):
    total_income: float = 0.0
    total_expense: float = 0.0
    balance: float = 0.0
    count: int = 0