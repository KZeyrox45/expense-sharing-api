from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    Pydantic-settings automatically reads the .env file and validates types.
    If a required variable is missing, a ValidationError will be raised upon app startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",        # Read from .env
        extra="ignore",         # Ignore extra env undeclared variables
        case_sensitive=False,   # DATABASE_URL == database_url
    )

    # --- App ---
    APP_ENV: str = "development"
    SECRET_KEY: str             # Mandatory, no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database ---
    DATABASE_URL: str           # Mandatory

    # --- Redis ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # --- Email ---
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@expensesharing.dev"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "sandbox.smtp.mailtrap.io"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    @property
    def is_production(self) -> bool:
        """Helper to check environment, use in logging and error handling."""
        return self.APP_ENV == "production"
    

settings = Settings()