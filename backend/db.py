"""
SQLAlchemy engine/session setup for Supabase Postgres.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    if not settings.supabase_db_url:
        raise RuntimeError("Missing SUPABASE_DB_URL. Add it to backend/.env.")

    return create_engine(
        settings.supabase_db_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db():
    try:
        session_factory = get_session_factory()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db = session_factory()
    try:
        yield db
    finally:
        db.close()
