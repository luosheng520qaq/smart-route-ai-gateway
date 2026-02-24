from sqlalchemy import Column, Integer, String, Text, Float, DateTime, event, case
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
    category = Column(String, default="unknown", index=True) # tool, chat, unknown

class ConfigHistory(Base):
    __tablename__ = "config_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    config_json = Column(Text) # Store full config as JSON
    change_reason = Column(String, nullable=True)
    user = Column(String, nullable=True) # Who made the change

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    totp_secret = Column(String, nullable=True)
    is_active = Column(Integer, default=1)

class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, index=True, unique=True)
    total_requests = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    total_duration_ms = Column(Float, default=0.0)
    total_prompt_tokens = Column(Integer, default=0)
    total_completion_tokens = Column(Integer, default=0)
    total_retries = Column(Integer, default=0)
    t1_count = Column(Integer, default=0)
    t2_count = Column(Integer, default=0)
    t3_count = Column(Integer, default=0)

async def update_daily_stats(log: RequestLog):
    from sqlalchemy import select, update
    
    date_str = log.timestamp.strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(DailyStats).where(DailyStats.date == date_str)
            )
            stats = result.scalars().first()
            
            if stats:
                stats.total_requests += 1
                if log.status == "success":
                    stats.success_count += 1
                else:
                    stats.error_count += 1
                stats.total_duration_ms += log.duration_ms
                stats.total_prompt_tokens += log.prompt_tokens
                stats.total_completion_tokens += log.completion_tokens
                stats.total_retries += log.retry_count
                
                if log.level == "t1":
                    stats.t1_count += 1
                elif log.level == "t2":
                    stats.t2_count += 1
                elif log.level == "t3":
                    stats.t3_count += 1
            else:
                stats = DailyStats(
                    date=date_str,
                    total_requests=1,
                    success_count=1 if log.status == "success" else 0,
                    error_count=0 if log.status == "success" else 1,
                    total_duration_ms=log.duration_ms,
                    total_prompt_tokens=log.prompt_tokens,
                    total_completion_tokens=log.completion_tokens,
                    total_retries=log.retry_count,
                    t1_count=1 if log.level == "t1" else 0,
                    t2_count=1 if log.level == "t2" else 0,
                    t3_count=1 if log.level == "t3" else 0
                )
                session.add(stats)
            
            await session.commit()
        except Exception as e:
            logging.error(f"Failed to update daily stats: {e}")
            await session.rollback()

async def migrate_historical_stats():
    from sqlalchemy import select, func, and_
    
    async with AsyncSessionLocal() as session:
        try:
            existing_dates = await session.execute(
                select(DailyStats.date)
            )
            existing_dates = set(r[0] for r in existing_dates.all())
            
            result = await session.execute(
                select(
                    func.date(RequestLog.timestamp).label('log_date'),
                    func.count(RequestLog.id).label('total'),
                    func.sum(case((RequestLog.status == "success", 1), else_=0)).label('success'),
                    func.sum(case((RequestLog.status != "success", 1), else_=0)).label('error'),
                    func.sum(RequestLog.duration_ms).label('duration'),
                    func.sum(RequestLog.prompt_tokens).label('prompt_tokens'),
                    func.sum(RequestLog.completion_tokens).label('completion_tokens'),
                    func.sum(RequestLog.retry_count).label('retries'),
                    func.sum(case((RequestLog.level == "t1", 1), else_=0)).label('t1'),
                    func.sum(case((RequestLog.level == "t2", 1), else_=0)).label('t2'),
                    func.sum(case((RequestLog.level == "t3", 1), else_=0)).label('t3')
                ).group_by(func.date(RequestLog.timestamp))
            )
            
            for row in result.all():
                date_str = row.log_date
                if date_str in existing_dates:
                    continue
                
                stats = DailyStats(
                    date=date_str,
                    total_requests=row.total or 0,
                    success_count=row.success or 0,
                    error_count=row.error or 0,
                    total_duration_ms=row.duration or 0.0,
                    total_prompt_tokens=row.prompt_tokens or 0,
                    total_completion_tokens=row.completion_tokens or 0,
                    total_retries=row.retries or 0,
                    t1_count=row.t1 or 0,
                    t2_count=row.t2 or 0,
                    t3_count=row.t3 or 0
                )
                session.add(stats)
            
            await session.commit()
            logging.info("Historical stats migration completed.")
        except Exception as e:
            logging.error(f"Failed to migrate historical stats: {e}")
            await session.rollback()

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

        try:
            await conn.execute(text("ALTER TABLE request_logs ADD COLUMN category TEXT DEFAULT 'unknown'"))
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
