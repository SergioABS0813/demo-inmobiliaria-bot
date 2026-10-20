from functools import lru_cache
from fastapi import HTTPException
from supabase import create_client
from .config import get_settings


@lru_cache
def get_db():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise HTTPException(503, "La conexión con el catálogo todavía no está configurada.")
    return create_client(settings.supabase_url, settings.supabase_secret_key)
