"""
Protected auth/chat routes backed by Supabase Auth and Postgres persistence.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user_claims, get_or_create_profile
from chat_service import (
    add_message,
    create_chat,
    get_user_chat,
    list_chat_messages,
    list_user_chats,
)
from db import get_db
from models import Profile
from schemas import (
    ChatCreateRequest,
    ChatMessageCreateRequest,
    ChatResponse,
    MeResponse,
    MessageResponse,
)

router = APIRouter()


def _current_profile(db: Session, claims: dict) -> Profile:
    return get_or_create_profile(db, claims)


@router.get("/auth/me", response_model=MeResponse, tags=["auth"])
async def auth_me(claims=Depends(get_current_user_claims), db: Session = Depends(get_db)):
    profile = _current_profile(db, claims)
    return MeResponse(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        avatar_url=profile.avatar_url,
    )


@router.post("/chats", response_model=ChatResponse, tags=["chats"])
async def create_chat_endpoint(
    request: ChatCreateRequest,
    claims=Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    profile = _current_profile(db, claims)
    chat = create_chat(db, profile, request.title)
    return ChatResponse.model_validate(chat, from_attributes=True)


@router.get("/chats", response_model=list[ChatResponse], tags=["chats"])
async def list_chats_endpoint(claims=Depends(get_current_user_claims), db: Session = Depends(get_db)):
    profile = _current_profile(db, claims)
    chats = list_user_chats(db, profile.id)
    return [ChatResponse.model_validate(chat, from_attributes=True) for chat in chats]


@router.get("/chats/{chat_id}/messages", response_model=list[MessageResponse], tags=["chats"])
async def list_chat_messages_endpoint(
    chat_id: UUID,
    claims=Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    profile = _current_profile(db, claims)
    chat = get_user_chat(db, profile.id, chat_id)
    messages = list_chat_messages(db, chat.id)
    return [MessageResponse.model_validate(message, from_attributes=True) for message in messages]


@router.post("/chats/{chat_id}/messages", response_model=MessageResponse, tags=["chats"])
async def create_chat_message_endpoint(
    chat_id: UUID,
    request: ChatMessageCreateRequest,
    claims=Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    profile = _current_profile(db, claims)
    chat = get_user_chat(db, profile.id, chat_id)
    message = add_message(
        db,
        chat=chat,
        user_id=profile.id if request.role == "user" else None,
        role=request.role,
        content=request.content,
    )
    return MessageResponse.model_validate(message, from_attributes=True)
