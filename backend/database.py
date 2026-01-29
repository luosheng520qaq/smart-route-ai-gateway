from sqlalchemy import Column, Integer, String, Text, Float, DateTime, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine
from datetime import datetime
import logging

DATABASE_URL = "sqlite+aiosqlite:///./logs.db"

# Enable WAL mode for better concurrency
engine = create_async_engine(DATABASE_URL, echo=False)

# Event listener to set WAL mode on connection
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    # Add index to timestamp for faster range queries and sorting
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String)  # T1, T2, T3
    model = Column(String)
    duration_ms = Column(Float)
    status = Column(String, index=True) # success, error, timeout
    user_prompt_preview = Column(Text)
    full_request = Column(Text) # JSON string
    full_response = Column(Text) # JSON string
    trace = Column(Text) # JSON string for timeline events

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Simple migration: check if 'trace' column exists, if not add it
        # Note: SQLite doesn't support IF NOT EXISTS in ALTER TABLE well for columns in all versions,
        # but SQLAlchemy sync methods usually handle create_all (only creates missing tables).
        # For adding a column to existing table, we need manual check or alembic.
        # Let's do a raw check and alter if needed.
        from sqlalchemy import text
        try:
            # Try to select the column to see if it exists
            await conn.execute(text("SELECT trace FROM request_logs LIMIT 1"))
        except Exception:
            # If failed, likely column missing
            try:
                await conn.execute(text("ALTER TABLE request_logs ADD COLUMN trace TEXT"))
                print("[INFO] Migrated database: Added 'trace' column.")
            except Exception as e:
                print(f"[WARN] Failed to add trace column (might already exist or other error): {e}")

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def prune_logs(days_retention: int = 7):
    """Prune logs older than days_retention."""
    from sqlalchemy import delete
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_retention)
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                delete(RequestLog).where(RequestLog.timestamp < cutoff_date)
            )
            await session.commit()
            # Vacuum to reclaim space (optional, can be expensive)
            # await session.execute("VACUUM") 
        except Exception as e:
            logging.error(f"Failed to prune logs: {e}")
