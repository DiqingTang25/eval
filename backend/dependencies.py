"""FastAPI 依赖注入 — MySQL 惰性引擎"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_async_engine = None
_async_session_factory = None
_sync_engine = None
_sync_session_factory = None


def _get_async_session_factory():
    global _async_engine, _async_session_factory
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.database_url, echo=False, pool_size=10, pool_recycle=3600
        )
        _async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    return _async_session_factory


def _get_sync_session_factory():
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        from sqlalchemy import create_engine
        _sync_engine = create_engine(
            settings.sync_database_url, echo=False, pool_recycle=3600
        )
        _sync_session_factory = sessionmaker(_sync_engine, expire_on_commit=False)
    return _sync_session_factory


def get_sync_db() -> Session:
    return _get_sync_session_factory()()


async def get_db() -> AsyncSession:
    factory = _get_async_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
