"""
Subscriptions Router — управління SaaS підписками через Stripe.
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionResponse, CheckoutRequest
from app.services.subscription_service import (
    create_checkout_session,
    handle_stripe_webhook,
    get_tier_info,
)

router = APIRouter(prefix="/subscription", tags=["subscriptions"])


@router.get("", response_model=dict)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Поточний стан підписки та ліміти."""
    from datetime import datetime, timezone

    tier_info = get_tier_info(current_user.subscription_tier)
    is_active = (
        current_user.subscription_tier != "free"
        and (
            current_user.subscription_expires_at is None
            or current_user.subscription_expires_at > datetime.now(timezone.utc)
        )
    )

    return {
        "tier": current_user.subscription_tier,
        "is_active": is_active,
        "expires_at": current_user.subscription_expires_at.isoformat() if current_user.subscription_expires_at else None,
        "limits": {
            "plots": current_user.plots_limit,
            "plants": current_user.plants_limit,
            "diagnoses_per_month": tier_info["diagnoses_per_month"],
            "photos_per_entry": tier_info["photos_per_entry"],
        },
        "features": tier_info["features"],
        "stripe_customer_id": current_user.stripe_customer_id,
    }


@router.post("/checkout")
async def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Створює Stripe Checkout Session та повертає URL для оплати."""
    checkout_url = await create_checkout_session(
        user_id=str(current_user.id),
        stripe_customer_id=current_user.stripe_customer_id,
        tier=data.tier,
        billing_cycle=data.billing_cycle,
        success_url=data.success_url,
        cancel_url=data.cancel_url,
    )
    return {"checkout_url": checkout_url}


@router.post("/cancel", status_code=204)
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Відміняє підписку (діє до кінця поточного оплаченого періоду)."""
    import stripe
    from app.config import settings

    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Активна Stripe підписка не знайдена")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    subscriptions = stripe.Subscription.list(customer=current_user.stripe_customer_id, status="active")

    for sub in subscriptions.data:
        stripe.Subscription.modify(sub.id, cancel_at_period_end=True)

    return None


@router.get("/history", response_model=list[dict])
async def get_subscription_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Історія підписок."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == current_user.id)
        .order_by(Subscription.started_at.desc())
    )
    subs = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "tier": s.tier,
            "status": s.status,
            "started_at": s.started_at.isoformat(),
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "price_usd": float(s.price_usd) if s.price_usd else None,
            "billing_cycle": s.billing_cycle,
        }
        for s in subs
    ]


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe Webhook — обробляє події оплати.
    Налаштуйте в Stripe Dashboard: checkout.session.completed,
    customer.subscription.deleted, invoice.payment_failed
    """
    payload = await request.body()
    try:
        result = await handle_stripe_webhook(payload, stripe_signature, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
