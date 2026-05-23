"""
Application configuration for local env-driven settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    tavily_api_key: str | None
    groq_api_key: str | None
    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_service_role_key: str | None
    supabase_db_url: str | None
    supabase_jwt_issuer: str | None


settings = Settings(
    tavily_api_key=os.getenv("TAVILY_API_KEY"),
    groq_api_key=os.getenv("GROQ_API_KEY"),
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_anon_key=os.getenv("SUPABASE_ANON_KEY"),
    supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    supabase_db_url=os.getenv("SUPABASE_DB_URL"),
    supabase_jwt_issuer=os.getenv("SUPABASE_JWT_ISSUER"),
)
