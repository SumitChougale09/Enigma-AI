"""
Pydantic schemas for auth and chat endpoints.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None


class ChatCreateRequest(BaseModel):
    title: str | None = None


class ChatMessageCreateRequest(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ChatResponse(BaseModel):
    id: UUID
    title: str
    last_message_preview: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    chat_id: UUID
    user_id: UUID | None = None
    role: str
    content: str
    created_at: datetime
