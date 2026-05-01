"""
Plant Profile Router — AI-powered agronomic data via PlantProfileService.

POST /api/v1/plant-profiles/lookup
  {"plant_name": "Персик", "category": "Фруктові дерева"}

Flow is centralized in app.services.plant_profile_service.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.plant_profile_service import lookup_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plant-profiles", tags=["plant-profiles"])


try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
    _has_limiter = True
except ImportError:
    limiter = None
    _has_limiter = False


def _rate_limit(limit_string: str):
    def decorator(func):
        if _has_limiter and limiter:
            return limiter.limit(limit_string)(func)
        return func

    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

class LookupRequest(BaseModel):
    plant_name: str
    category: str = "Овочі"


@router.post("/lookup")
@_rate_limit(settings.GEMINI_PROFILE_LOOKUP_RATE_LIMIT)
async def lookup_plant_profile(
    request: Request,
    req: LookupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = req.plant_name.strip()
    if not name:
        raise HTTPException(400, "Назва не може бути порожньою")

    return await lookup_profile(name, req.category, db)
