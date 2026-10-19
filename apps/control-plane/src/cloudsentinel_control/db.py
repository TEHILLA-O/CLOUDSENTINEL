from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from cloudsentinel_control.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["pool_pre_ping"] = False
        # :memory: would give each connection its own database. A file, or a
        # single static pool, keeps the control-plane state visible across sessions.
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(database_url, **kwargs)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_database(engine: AsyncEngine) -> None:
    if engine.url.get_backend_name() == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
