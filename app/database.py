"""
ApexMarket: Asynchronous Database and Redis Client Management
Configures SQLAlchemy AsyncSession connection pooling and Redis asynchronous clients.
"""

from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.config import get_settings

settings = get_settings()

Base = declarative_base()

# Async PostgreSQL Engine & Sessionmaker
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.APP_ENV == "development" and settings.LOG_LEVEL == "DEBUG"),
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"timeout": 2.0} if "postgresql" in settings.DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Async Redis Client
_redis_client: Optional[aioredis.Redis] = None
_postgres_available: Optional[bool] = None


async def is_postgres_available() -> bool:
    """Checks whether the PostgreSQL database is reachable."""
    global _postgres_available
    if _postgres_available is False:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _postgres_available = True
        return True
    except Exception:
        _postgres_available = False
        return False


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a transactional async database session.
    Automatically handles rollback on unhandled exceptions and session closure.
    Gracefully falls back to an in-memory session if PostgreSQL is unreachable.
    """
    if await is_postgres_available():
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    else:
        from app.services.in_memory_store import get_in_memory_session
        session = get_in_memory_session()
        try:
            yield session
        finally:
            await session.close()


async def get_redis_client() -> aioredis.Redis:
    """Returns or initializes the singleton asynchronous Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    return _redis_client


async def close_database_connections() -> None:
    """Gracefully shuts down database and Redis connection pools."""
    global _redis_client
    if _redis_client is not None:
        if hasattr(_redis_client, "aclose"):
            await _redis_client.aclose()
        else:
            await _redis_client.close()
        _redis_client = None
    if engine is not None:
        await engine.dispose()
