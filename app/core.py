
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# ============================================================
# APPLICATION SETTINGS
# ============================================================

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./telecom.db"

    # Security configuration
    # No insecure default secret.
    secret_key: str = Field(min_length=32)

    # API rate limiting
    rate_limit: str = "120/minute"
    plans_rate_limit: str = "200/minute"

    # Redis cache configuration
    redis_url: str = "redis://localhost:6379/0"

    plan_cache_ttl_seconds: int = Field(
        default=60,
        gt=0,
        le=3600,
    )


settings = Settings()


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args=(
        {"check_same_thread": False}
        if is_sqlite
        else {}
    ),
    pool_pre_ping=True,
)


# ============================================================
# SQLITE FOREIGN KEY SUPPORT
# ============================================================

if is_sqlite:

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection,
        connection_record,
    ):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ============================================================
# DATABASE SESSION
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=True,
)


# ============================================================
# SQLALCHEMY BASE
# ============================================================

class Base(DeclarativeBase):
    pass


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
