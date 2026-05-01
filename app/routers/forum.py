"""Forum Router — community forum."""
from uuid import UUID
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.forum import ForumTopic, ForumReply
from app.schemas.forum import (
    ForumTopicCreate, ForumTopicListItem, ForumTopicDetail,
    ForumReplyCreate, ForumReplyResponse,
)

router = APIRouter(prefix="/forum", tags=["forum"])
logger = logging.getLogger(__name__)

AVAILABLE_TAGS = [
    "Загальне", "Овочі", "Ягоди", "Дерева", "Захист рослин",
    "Полив", "Ґрунт", "Добрива", "Інструменти", "Рецепти",
    "Фінанси", "Питання новачкам",
]

@router.get("/tags")
async def get_tags():
    return AVAILABLE_TAGS

@router.get("/topics", response_model=list[ForumTopicListItem])
async def list_topics(
    tag: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    query = select(ForumTopic).options(selectinload(ForumTopic.author)).where(ForumTopic.is_deleted.is_(False)).order_by(
        ForumTopic.is_pinned.desc(), ForumTopic.created_at.desc()
    ).offset((page - 1) * size).limit(size)
    if tag:
        query = query.where(ForumTopic.tag == tag)
    return (await db.execute(query)).scalars().all()

@router.post("/topics", response_model=ForumTopicListItem, status_code=201)
async def create_topic(
    data: ForumTopicCreate, current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = ForumTopic(user_id=current_user.id, title=data.title, body=data.body,
        tag=data.tag if data.tag in AVAILABLE_TAGS else "Загальне")
    db.add(topic); await db.commit(); await db.refresh(topic)
    return await db.scalar(select(ForumTopic).options(
        selectinload(ForumTopic.author),
    ).where(ForumTopic.id == topic.id))

@router.get("/topics/{topic_id}", response_model=ForumTopicDetail)
async def get_topic(
    topic_id: UUID, current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = await db.scalar(select(ForumTopic).options(
        selectinload(ForumTopic.author),
        selectinload(ForumTopic.replies).selectinload(ForumReply.author),
    ).where(ForumTopic.id == topic_id, ForumTopic.is_deleted.is_(False)))
    if not topic:
        raise HTTPException(404, "Topic not found")
    topic.views_count += 1; await db.commit()
    return topic

@router.get("/topics/{topic_id}/replies", response_model=list[ForumReplyResponse])
async def list_replies(
    topic_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic_exists = await db.scalar(select(ForumTopic.id).where(
        ForumTopic.id == topic_id, ForumTopic.is_deleted.is_(False)))
    if not topic_exists:
        raise HTTPException(404, "Topic not found")
    result = await db.execute(select(ForumReply).options(
        selectinload(ForumReply.author),
    ).where(
        ForumReply.topic_id == topic_id,
        ForumReply.is_deleted.is_(False),
    ).order_by(ForumReply.created_at.asc()).offset((page - 1) * size).limit(size))
    return result.scalars().all()

@router.post("/topics/{topic_id}/replies", response_model=ForumReplyResponse, status_code=201)
async def add_reply(
    topic_id: UUID, data: ForumReplyCreate,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    topic = await db.scalar(select(ForumTopic).where(
        ForumTopic.id == topic_id, ForumTopic.is_deleted.is_(False)))
    if not topic:
        raise HTTPException(404, "Topic not found")
    reply = ForumReply(topic_id=topic_id, user_id=current_user.id, body=data.body)
    db.add(reply); topic.replies_count += 1; await db.commit(); await db.refresh(reply)
    return await db.scalar(select(ForumReply).options(
        selectinload(ForumReply.author),
    ).where(ForumReply.id == reply.id))

@router.post("/topics/{topic_id}/reply", response_model=ForumReplyResponse, status_code=201)
async def add_reply_legacy(
    topic_id: UUID, data: ForumReplyCreate,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await add_reply(topic_id, data, current_user, db)

@router.delete("/topics/{topic_id}", status_code=204)
async def delete_topic(
    topic_id: UUID, current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = await db.scalar(select(ForumTopic).where(
        ForumTopic.id == topic_id, ForumTopic.is_deleted.is_(False)))
    if not topic:
        raise HTTPException(404, "Topic not found")
    if topic.user_id != current_user.id:
        raise HTTPException(403, "Можна видалити тільки свою тему")
    topic.is_deleted = True; await db.commit()
