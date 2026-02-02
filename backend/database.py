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
    stack_trace = Column(Text) # Error stack trace
    retry_count = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    token_source = Column(String, default="upstream") # upstream / local

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    totp_secret = Column(String, nullable=True) # 2FA Secret
    is_active = Column(Integer, default=1) # 1: Active, 0: Inactive

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Manual migration for new columns
        from sqlalchemy import text
        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN trace TEXT"))
        except Exception:
            pass # Already exists
            
        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN stack_trace TEXT"))
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN retry_count INTEGER DEFAULT 0"))
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN prompt_tokens INTEGER DEFAULT 0"))
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN completion_tokens INTEGER DEFAULT 0"))
        except Exception:
            pass # Already exists

        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN token_source TEXT DEFAULT 'upstream'"))
        except Exception:
            pass # Already exists

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
