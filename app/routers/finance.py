"""
Finance Router — full CRUD for income/expense tracking.

Endpoints:
  POST   /finance/transactions           — create
  GET    /finance/transactions           — list (newest first)
  PUT    /finance/transactions/{id}      — update
  DELETE /finance/transactions/{id}      — delete
  GET    /finance/stats                  — aggregated stats
"""
from uuid import UUID
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.finance import FinanceTransaction
from app.schemas.finance import (
    FinanceTransactionCreate,
    FinanceTransactionUpdate,
    FinanceTransactionResponse,
    FinanceStatsResponse,
)

router = APIRouter(prefix="/finance", tags=["finance"])
logger = logging.getLogger(__name__)


def _to_response(txn: FinanceTransaction) -> FinanceTransactionResponse:
    return FinanceTransactionResponse(
        id=txn.id,
        type=txn.type,
        amount=float(txn.amount),
        plot=txn.plot,
        category=txn.category,
        note=txn.note,
        date=txn.date,
        created_at=txn.created_at,
    )


async def _get_txn_or_404(
    txn_id: UUID, user_id, db: AsyncSession
) -> FinanceTransaction:
    txn = await db.scalar(
        select(FinanceTransaction).where(
            FinanceTransaction.id == txn_id,
            FinanceTransaction.user_id == user_id,
        )
    )
    if not txn:
        raise HTTPException(404, "Транзакцію не знайдено")
    return txn


# ── POST ──────────────────────────────────────────────────────────────────────

@router.post("/transactions", response_model=FinanceTransactionResponse, status_code=201)
async def create_transaction(
    data: FinanceTransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    txn = FinanceTransaction(
        user_id=current_user.id,
        type=data.type,
        amount=data.amount,
        plot=data.plot,
        category=data.category,
        note=data.note,
        date=data.date or datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    logger.info("Finance: %s %.2f by %s", data.type, data.amount, current_user.id)
    return _to_response(txn)


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("/transactions", response_model=list[FinanceTransactionResponse])
async def list_transactions(
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(FinanceTransaction)
        .where(FinanceTransaction.user_id == current_user.id)
        .order_by(FinanceTransaction.date.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = (await db.scalars(stmt)).all()
    return [_to_response(r) for r in rows]


# ── PUT ───────────────────────────────────────────────────────────────────────

@router.put("/transactions/{txn_id}", response_model=FinanceTransactionResponse)
async def update_transaction(
    txn_id: UUID,
    data: FinanceTransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    txn = await _get_txn_or_404(txn_id, current_user.id, db)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(txn, field, value)
    await db.commit()
    await db.refresh(txn)
    logger.info("Finance updated: %s", txn_id)
    return _to_response(txn)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete("/transactions/{txn_id}", status_code=204)
async def delete_transaction(
    txn_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    txn = await _get_txn_or_404(txn_id, current_user.id, db)
    await db.delete(txn)
    await db.commit()
    logger.info("Finance deleted: %s", txn_id)


# ── GET stats ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=FinanceStatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = current_user.id

    income_q = select(
        sa_func.coalesce(sa_func.sum(FinanceTransaction.amount), 0)
    ).where(FinanceTransaction.user_id == uid, FinanceTransaction.type == "income")

    expense_q = select(
        sa_func.coalesce(sa_func.sum(FinanceTransaction.amount), 0)
    ).where(FinanceTransaction.user_id == uid, FinanceTransaction.type == "expense")

    count_q = select(
        sa_func.count(FinanceTransaction.id)
    ).where(FinanceTransaction.user_id == uid)

    total_income = float(await db.scalar(income_q) or 0)
    total_expense = float(await db.scalar(expense_q) or 0)
    count = int(await db.scalar(count_q) or 0)

    return FinanceStatsResponse(
        total_income=total_income,
        total_expense=total_expense,
        balance=total_income - total_expense,
        count=count,
    )