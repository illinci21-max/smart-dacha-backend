"""
Universal pagination wrapper for list endpoints.

FIX from Code Review §4.1:
  Endpoints returned bare list[] without metadata.
  Now all list endpoints return {items, total, page, size, has_next}.

Usage in router:
    from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate

    @router.get("", response_model=PaginatedResponse[PlotResponse])
    async def list_plots(
        params: PaginationParams = Depends(),
        ...
    ):
        return await paginate(db, select(Plot).where(...), params)
"""
from __future__ import annotations

from typing import Generic, TypeVar, Sequence
from pydantic import BaseModel
from fastapi import Query
from sqlalchemy import select, func, Select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginationParams:
    """Extracts page/size from query string with sensible defaults."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        size: int = Query(20, ge=1, le=200, description="Items per page"),
    ):
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope."""

    items: list[T]
    total: int
    page: int
    size: int
    has_next: bool


async def paginate(
    db: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> dict:
    """
    Execute a query with pagination, returning dict compatible with
    PaginatedResponse schema.

    Args:
        db: async database session
        query: SQLAlchemy select statement (WITHOUT limit/offset)
        params: pagination parameters from query string
    """
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    paginated = query.offset(params.offset).limit(params.size)
    result = await db.execute(paginated)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": params.page,
        "size": params.size,
        "has_next": (params.page * params.size) < total,
    }
