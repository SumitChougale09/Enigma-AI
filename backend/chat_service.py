"""
Basic chat persistence helpers.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from models import Chat, Message, Profile


def create_chat(db: Session, user: Profile, title: str | None = None) -> Chat:
    chat = Chat(user_id=user.id, title=title or "New chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def get_user_chat(db: Session, user_id: UUID, chat_id: UUID) -> Chat:
    chat = db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def list_user_chats(db: Session, user_id: UUID) -> list[Chat]:
    return list(
        db.scalars(
            select(Chat).where(Chat.user_id == user_id).order_by(desc(Chat.updated_at))
        )
    )


def list_chat_messages(db: Session, chat_id: UUID) -> list[Message]:
    return list(
        db.scalars(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
        )
    )


def add_message(
    db: Session,
    *,
    chat: Chat,
    user_id: UUID | None,
    role: str,
    content: str,
) -> Message:
    message = Message(
        chat_id=chat.id,
        user_id=user_id,
        role=role,
        content=content,
    )
    db.add(message)
    chat.last_message_preview = content[:280]
    if chat.title == "New chat" and role == "user":
        chat.title = content[:80]
    db.commit()
    db.refresh(message)
    db.refresh(chat)
    return message
