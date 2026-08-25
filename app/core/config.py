from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "System Lab POS API"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"

    DATABASE_URL: str = "postgresql://postgres:naza1808@127.0.0.1:5432/systemlab_pos"

    JWT_SECRET_KEY: str = "change-this-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Lista separada por comas. En Render puede sobrescribirse con CORS_ORIGINS.
    CORS_ORIGINS: str = (
        "http://localhost:4200,http://127.0.0.1:4200,"
        "https://systemlabcr.com,https://www.systemlabcr.com"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
