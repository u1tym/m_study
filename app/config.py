from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_server: str = "localhost"
    db_name: str = "tamtdb"
    db_port: int = 5432
    db_username: str = "tamtuser"
    db_password: str = "TAMTTAMT"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_cookie_name: str = "access_token"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
