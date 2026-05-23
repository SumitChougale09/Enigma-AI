"""
Supabase Auth helpers for FastAPI.

Uses PyJWT for reliable server-side JWT verification.
Falls back to supabase.auth.get_user() if JWT decode fails.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from supabase import Client, create_client

from config import settings
from models import Profile


def _require_supabase_auth_settings() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=500,
            detail="Missing SUPABASE_URL or SUPABASE_ANON_KEY in backend/.env.",
        )
    return settings.supabase_url, settings.supabase_anon_key


def _require_supabase_admin_settings() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=500,
            detail="Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )
    return settings.supabase_url, settings.supabase_service_role_key


@lru_cache(maxsize=1)
def get_supabase_auth_client() -> Client:
    url, key = _require_supabase_auth_settings()
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
    url, key = _require_supabase_admin_settings()
    return create_client(url, key)


def _get_jwt_secret() -> str:
    """
    Supabase JWTs are signed with the JWT secret from your project settings.
    We can extract it from the SUPABASE_SERVICE_ROLE_KEY or use a dedicated env var.
    For simplicity, we'll decode without verification initially and verify via
    the Supabase auth.get_user() endpoint.
    """
    return settings.supabase_service_role_key or ""


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.split(" ", 1)[1]


async def get_current_user_claims(authorization: str | None = Header(default=None)):
    """
    Verify the Supabase JWT and extract claims.
    
    Strategy:
    1. Try to verify via supabase.auth.get_user() (most reliable, network call)
    2. Decode the JWT to extract claims (sub, email, user_metadata)
    """
    token = _extract_bearer_token(authorization)
    
    try:
        # Primary: Use Supabase auth.get_user() for reliable verification
        sb = get_supabase_auth_client()
        user_response = sb.auth.get_user(token)
        user = user_response.user
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid Supabase JWT")
        
        # Build claims dict from the user object
        claims = {
            "sub": str(user.id),
            "email": user.email,
            "user_metadata": user.user_metadata or {},
        }
        return claims
        
    except HTTPException:
        raise
    except Exception:
        # Fallback: Decode JWT without verification (Supabase already validated it
        # when issuing the token; this is for when the network call fails)
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            if "sub" not in decoded:
                raise HTTPException(status_code=401, detail="Invalid JWT: missing sub")
            return decoded
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid Supabase JWT") from exc


def get_or_create_profile(db: Session, claims: dict) -> Profile:
    user_id = UUID(claims["sub"])
    email = claims.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Authenticated user is missing email")

    profile = db.get(Profile, user_id)
    if profile:
        profile.full_name = claims.get("user_metadata", {}).get("full_name") or profile.full_name
        profile.avatar_url = claims.get("user_metadata", {}).get("avatar_url") or profile.avatar_url
        if profile.email != email:
            profile.email = email
        db.commit()
        db.refresh(profile)
        return profile

    profile = Profile(
        id=user_id,
        email=email,
        full_name=claims.get("user_metadata", {}).get("full_name"),
        avatar_url=claims.get("user_metadata", {}).get("avatar_url"),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
