from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change_me_ruggylab_super_secret_key"
DEFAULT_FIRST_SUPERUSER_PASSWORD = "change_me_admin_password"


class Settings(BaseSettings):
    APP_NAME: str = "RuggyLab OS"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "postgresql+psycopg://admin:changeme_ruggylab@localhost:5432/ruggylab_os"
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = DEFAULT_FIRST_SUPERUSER_PASSWORD
    FIRST_SUPERUSER_FULL_NAME: str = "RuggyLab Administrator"
    ENABLE_DH36_LISTENER: bool = True
    TESTING: bool = False
    DH36_LISTENER_HOST: str = "0.0.0.0"
    DH36_LISTENER_PORT: int = 5001
    BASE_DATA_DIR: str = "data"
    MICROSCOPY_STORAGE_DIR: str = "data/microscopy"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def has_default_secret_key(self) -> bool:
        return self.SECRET_KEY == DEFAULT_SECRET_KEY

    @property
    def has_default_superuser_password(self) -> bool:
        return self.FIRST_SUPERUSER_PASSWORD == DEFAULT_FIRST_SUPERUSER_PASSWORD

    @property
    def requires_security_hardening(self) -> bool:
        weak_secret = len(self.SECRET_KEY) < 32 or "change_me" in self.SECRET_KEY.lower()
        weak_admin_password = len(self.FIRST_SUPERUSER_PASSWORD) < 16 or "change_me" in self.FIRST_SUPERUSER_PASSWORD.lower()
        return weak_secret or weak_admin_password


settings = Settings()
