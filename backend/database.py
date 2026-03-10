from sqlalchemy import Column, Integer, String, Text, Float, DateTime, event, case
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine
from datetime import datetime, timedelta
import logging
import pytz

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

def get_local_now():
    return datetime.now()

def get_local_date_str(dt: datetime = None):
    if dt is None:
        dt = get_local_now()
    return dt.strftime("%Y-%m-%d")

def utc_to_local(utc_dt: datetime):
    if utc_dt is None:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    return utc_dt.astimezone()

async def recalculate_daily_stats(date_str: str = None):
    from sqlalchemy import select, func, and_, delete
    
    if date_str is None:
        date_str = get_local_date_str()
    
    async with AsyncSessionLocal() as session:
        try:
            local_today_start = datetime.strptime(date_str, "%Y-%m-%d")
            local_today_end = local_today_start + timedelta(days=1)
            
            import pytz
            local_tz = datetime.now().astimezone().tzinfo
            utc_today_start = local_today_start.replace(tzinfo=local_tz).astimezone(pytz.utc).replace(tzinfo=None)
            utc_today_end = local_today_end.replace(tzinfo=local_tz).astimezone(pytz.utc).replace(tzinfo=None)
            
            result = await session.execute(
                select(
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
                ).where(
                    and_(
                        RequestLog.timestamp >= utc_today_start,
                        RequestLog.timestamp < utc_today_end
                    )
                )
            )
            
            row = result.one()
            
            await session.execute(
                delete(DailyStats).where(DailyStats.date == date_str)
            )
            
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
            logging.info(f"Recalculated daily stats for {date_str}")
        except Exception as e:
            logging.error(f"Failed to recalculate daily stats: {e}")
            await session.rollback()

async def update_daily_stats(log: RequestLog):
    local_timestamp = utc_to_local(log.timestamp)
    date_str = get_local_date_str(local_timestamp)
    await recalculate_daily_stats(date_str)

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
