from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    supabase_url: str
    supabase_secret_key: str
    initial_visit_state: str = "Pendiente de coordinación"
    requested_opportunity_state: str = "visita_solicitada"
    privacy_contact: str
    admin_username: str = "agente"
    admin_password: SecretStr | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings():
    return Settings()
