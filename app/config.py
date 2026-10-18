from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./lra_dev.db"  # use Postgres in real runs
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720
    pairing_code_ttl_seconds: int = 300
    anthropic_api_key: str = ""


settings = Settings()
