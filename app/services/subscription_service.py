"""
Subscription Service — управління SaaS підписками через Stripe.
FIX: _mark_subscription_past_due шукав по stripe_subscription_id а не customer_id
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import stripe
import logging

from app.config import settings

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

TIER_LIMITS = {
    "free": {
        "plots_limit": 999,
        "plants_limit": 9999,
        "diagnoses_per_week": 3,
        "diagnoses_per_month": 12,
        "photos_per_entry": 100,
        "features": [
            "crop_catalog", "care_journal_full", "weather_forecast_14d",
            "sat_tracking", "smart_watering", "push_notifications",
            "ai_diagnosis", "export_data", "custom_crops", "forum",
            "biodynamic_calendar",
        ],
    },
    "premium": {
        "plots_limit": 10,
        "plants_limit": 100,
        "diagnoses_per_month": 50,
        "photos_per_entry": 20,
        "features": [
            "crop_catalog", "care_journal_full", "weather_forecast_7d",
            "sat_tracking", "smart_watering", "push_notifications",
            "ai_diagnosis", "export_data",
        ],
    },
    "premium_plus": {
        "plots_limit": 999,
        "plants_limit": 9999,
        "diagnoses_per_month": 500,
        "photos_per_entry": 100,
        "features": [
            "crop_catalog", "care_journal_full", "weather_forecast_14d",
            "sat_tracking", "smart_watering", "push_notifications",
            "ai_diagnosis_priority", "export_data", "api_access",
            "custom_crops", "team_sharing",
        ],
    },
}


async def create_checkout_session(
    user_id: str,
    stripe_customer_id: Optional[str],
    tier: str,
    billing_cycle: str,
    success_url: str,
    cancel_url: str,
) -> str:
    price_id = (
        settings.STRIPE_PREMIUM_PRICE_ID
        if tier == "premium"
        else settings.STRIPE_PREMIUM_PLUS_PRICE_ID
    )

    # FIX: Валідація tier перед зверненням до Stripe
    if tier not in ("premium", "premium_plus"):
        raise ValueError(f"Invalid tier: {tier}")
    if not price_id:
        raise ValueError(f"Price ID for tier '{tier}' is not configured")

    session_params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"user_id": user_id, "tier": tier},
        "subscription_data": {"metadata": {"user_id": user_id}},
    }

    if stripe_customer_id:
        session_params["customer"] = stripe_customer_id

    session = stripe.checkout.Session.create(**session_params)
    return session.url


async def handle_stripe_webhook(payload: bytes, sig_header: str, db) -> dict:
    from sqlalchemy import select, update
    from app.models.user import User
    from app.models.subscription import Subscription

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid Stripe signature")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info(f"Stripe webhook: {event_type}, id={event.get('id')}")

    if event_type == "checkout.session.completed":
        user_id = data["metadata"].get("user_id")
        tier = data["metadata"].get("tier", "premium")
        customer_id = data.get("customer")
        stripe_sub_id = data.get("subscription")  # FIX: зберігаємо subscription ID

        if user_id:
            await _activate_subscription(db, user_id, tier, customer_id, stripe_sub_id)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        await _deactivate_subscription(db, customer_id)

    elif event_type == "invoice.payment_failed":
        # FIX: invoice має customer, а не subscription_id напряму
        customer_id = data.get("customer")
        stripe_sub_id = data.get("subscription")
        await _mark_subscription_past_due(db, stripe_sub_id)

    return {"status": "handled", "event": event_type}


async def _activate_subscription(
    db, user_id: str, tier: str, customer_id: str, stripe_sub_id: Optional[str] = None
):
    from sqlalchemy import update
    from app.models.user import User
    from app.models.subscription import Subscription

    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            subscription_tier=tier,
            subscription_expires_at=expires,
            stripe_customer_id=customer_id,
            plots_limit=limits["plots_limit"],
            plants_limit=limits["plants_limit"],
        )
    )

    # FIX: Записуємо в таблицю subscriptions для аудиту
    if stripe_sub_id:
        sub = Subscription(
            user_id=user_id,
            tier=tier,
            status="active",
            started_at=now,
            expires_at=expires,
            stripe_subscription_id=stripe_sub_id,
        )
        db.add(sub)

    await db.commit()
    logger.info(f"Activated {tier} for user {user_id}")


async def _deactivate_subscription(db, customer_id: str):
    from sqlalchemy import update
    from app.models.user import User

    free_limits = TIER_LIMITS["free"]
    await db.execute(
        update(User)
        .where(User.stripe_customer_id == customer_id)
        .values(
            subscription_tier="free",
            subscription_expires_at=None,
            plots_limit=free_limits["plots_limit"],
            plants_limit=free_limits["plants_limit"],
        )
    )
    await db.commit()


async def _mark_subscription_past_due(db, stripe_sub_id: str):
    """FIX: Шукаємо по stripe_subscription_id (не customer)"""
    from sqlalchemy import update
    from app.models.subscription import Subscription

    if not stripe_sub_id:
        return

    await db.execute(
        update(Subscription)
        .where(Subscription.stripe_subscription_id == stripe_sub_id)
        .values(status="past_due")
    )
    await db.commit()


def get_tier_info(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])
