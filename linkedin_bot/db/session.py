"""Async database session management with SQLAlchemy 2.0.

Replaces global mutable state with a DatabaseManager singleton.
Uses aiosqlite with WAL mode for concurrent reads.
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from linkedin_bot.db.models import Base
from linkedin_bot.logger import get_logger

log = get_logger(__name__)


class DatabaseManager:
    """Encapsulates async database engine and session factory.

    Replaces global mutable state (DEBT-001) with a proper singleton
    that can be initialized once and reused throughout the application.
    """

    _instance: DatabaseManager | None = None

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def get_instance(cls) -> DatabaseManager:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def init(self, db_path: str = "logs/bot_database.db") -> None:
        """Initialize the database engine and create tables.

        Args:
            db_path: Path to the SQLite database file.
        """
        db_url = f"sqlite+aiosqlite:///{db_path}"
        self._engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self._engine.begin() as conn:
            # Enable WAL mode for concurrent reads
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.run_sync(Base.metadata.create_all)

        log.info("database_initialized", path=db_path)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Provide a transactional async session.

        Yields:
            AsyncSession bound to a transaction.

        Raises:
            RuntimeError: If database has not been initialized.
        """
        if self._session_maker is None:
            msg = "Database not initialized. Call init() first."
            raise RuntimeError(msg)

        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as exc:
                await session.rollback()
                log.error("database_transaction_error", error=str(exc))
                raise


# ── Module-level convenience functions ──

async def init_db(db_path: str = "logs/bot_database.db") -> None:
    """Initialize the database (convenience wrapper).

    Args:
        db_path: Path to the SQLite database file.
    """
    manager = DatabaseManager.get_instance()
    await manager.init(db_path)


def get_db_session() -> AbstractAsyncContextManager[AsyncSession]:
    """Get an async database session context manager (convenience wrapper).

    Returns:
        Async context manager yielding an AsyncSession.
    """
    manager = DatabaseManager.get_instance()
    return manager.get_session()
