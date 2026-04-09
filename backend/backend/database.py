from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_wal_mode(dbapi_connection, connection_record):
    """Enable WAL mode for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with async_session() as session:
        yield session


async def init_db() -> None:
    """Create all tables from the metadata on startup."""
    from backend.models import Base  # noqa: F811

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migrate existing databases: add trigger column if missing
        columns = await conn.execute(text("PRAGMA table_info(scrape_jobs)"))
        column_names = [row[1] for row in columns]
        if "trigger" not in column_names:
            await conn.execute(
                text(
                    "ALTER TABLE scrape_jobs ADD COLUMN trigger TEXT NOT NULL DEFAULT 'manual'"
                )
            )
