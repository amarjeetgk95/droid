"""Supabase / PostgreSQL repositories bridge.

All repositories are now backed by Supabase PostgreSQL in `app.repositories`.
"""
from app.repositories.ml_repository import MLRepository
from app.repositories.ai_repository import AIRepository

__all__ = ["MLRepository", "AIRepository"]
