"""Forum schemas for API."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, UUID4, Field

class ForumTopicCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    body: str = Field(..., min_length=5, max_length=5000)
    tag: str = Field(default="Загальне", max_length=50)

class ForumReplyCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=3000)

class ForumAuthor(BaseModel):
    id: UUID4
    full_name: str | None = None
    email: str
    class Config:
        from_attributes = True

class ForumReplyResponse(BaseModel):
    id: UUID4
    body: str
    author: ForumAuthor
    created_at: datetime
    class Config:
        from_attributes = True

class ForumTopicListItem(BaseModel):
    id: UUID4
    title: str
    body: str
    tag: str
    author: ForumAuthor
    views_count: int = 0
    replies_count: int = 0
    is_pinned: bool = False
    created_at: datetime
    class Config:
        from_attributes = True

class ForumTopicDetail(BaseModel):
    id: UUID4
    title: str
    body: str
    tag: str
    author: ForumAuthor
    views_count: int = 0
    replies_count: int = 0
    is_pinned: bool = False
    created_at: datetime
    replies: list[ForumReplyResponse] = []
    class Config:
        from_attributes = True
