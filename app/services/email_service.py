"""Small SMTP email helper for account notifications."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and settings.SMTP_FROM_EMAIL
    )


async def send_password_reset_email(email: str) -> bool:
    if not smtp_configured():
        logger.warning("SMTP is not configured; password reset email skipped")
        return False

    subject = "Відновлення доступу до Smart Gardener"
    body = (
        "Ви запросили відновлення доступу до Smart Gardener.\n\n"
        "Якщо це були ви, зверніться до адміністратора або напишіть у підтримку, "
        "щоб змінити пароль безпечно.\n\n"
        "Якщо ви не робили цей запит, просто проігноруйте цей лист.\n\n"
        "Розумний Дачник"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = email
    message.set_content(body)

    try:
        await asyncio.to_thread(_send_message, message)
        return True
    except Exception:
        logger.exception("Password reset email failed")
        return False


def _send_message(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
