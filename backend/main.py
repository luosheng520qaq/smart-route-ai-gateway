from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks, Security, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select, desc, func, and_
from datetime import datetime, timedelta, timezone
import csv
import io
from contextlib import asynccontextmanager
import json
import os

from config_manager import config_manager, AppConfig
from database import init_db, get_db, RequestLog, AsyncSession, prune_logs
from router_engine import router_engine, ChatCompletionRequest
from logger import trace_logger

# Security
security = HTTPBearer(auto_error=False)

async def verify_gateway_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    config = config_manager.get_config()
    gateway_key = config.gateway_api_key
    
    # If no key configured, allow all
    if not gateway_key:
        return True
        
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if credentials.credentials != gateway_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid Gateway API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await init_db()
    # Initialize Router Engine (HTTP Client)
    await router_engine.startup()
    
    # Prune logs on startup based on config
    try:
        config = config_manager.get_config()
        days = config.log_retention_days
        await prune_logs(days)
        print(f"[INFO] Pruned logs older than {days} days on startup.")
    except Exception as e:
        print(f"[ERROR] Failed to prune logs on startup: {e}")
    yield
    # Shutdown logic
    await router_engine.shutdown()

app = FastAPI(title="SmartRoute AI Gateway", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket for Terminal ---
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await trace_logger.connect(websocket)
    try:
        while True:
            # Keep connection alive, maybe handle incoming commands (filter etc) in future
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        trace_logger.disconnect(websocket)

# --- OpenAI Protocol ---
@app.post("/v1/chat/completions", dependencies=[Depends(verify_gateway_key)])
async def chat_completions(request: ChatCompletionRequest, background_tasks: BackgroundTasks):
    return await router_engine.route_request(request, background_tasks)

@app.get("/v1/models", dependencies=[Depends(verify_gateway_key)])
async def list_models():
    config = config_manager.get_config()
    all_models = set(config.t1_models + config.t2_models + config.t3_models)
    
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(datetime.utcnow().timestamp()),
                "owned_by": "smart-route"
            }
            for model_id in all_models if model_id
        ]
    }

# --- Management API ---

@app.get("/api/config", dependencies=[Depends(verify_gateway_key)])
async def get_config():
    return config_manager.get_config()

@app.get("/api/stats/models", dependencies=[Depends(verify_gateway_key)])
async def get_model_stats():
    return router_engine.get_all_stats()

@app.post("/api/config", dependencies=[Depends(verify_gateway_key)])
async def update_config(config: AppConfig):
    try:
        config_manager.update_config(config.model_dump())
        # Cleanup stats for removed models
        router_engine.cleanup_stats()
        return {"status": "success", "config": config_manager.get_config()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", dependencies=[Depends(verify_gateway_key)])
async def get_logs(
    page: int = 1, 
    page_size: int = 20,
    level: Optional[str] = None,
    status: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    
    # Build Query
    stmt = select(RequestLog).order_by(desc(RequestLog.timestamp))
    
    conditions = []
    if level:
        conditions.append(RequestLog.level == level)
    if status:
        conditions.append(RequestLog.status == status)
    if model:
        conditions.append(RequestLog.model.contains(model))
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            conditions.append(RequestLog.timestamp >= sd.replace(tzinfo=None))
        except: pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            conditions.append(RequestLog.timestamp <= ed.replace(tzinfo=None))
        except: pass
        
    if conditions:
        stmt = stmt.where(and_(*conditions))
    
    # Execute Count
    count_stmt = select(func.count(RequestLog.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    count_result = await db.execute(count_stmt)
    total = count_result.scalar()
    
    # Execute Main Query
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs
    }

@app.get("/api/logs/export", dependencies=[Depends(verify_gateway_key)])
async def export_logs(
    level: Optional[str] = None,
    status: Optional[str] = None,
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Build Query (Same as above but no pagination)
    stmt = select(RequestLog).order_by(desc(RequestLog.timestamp))
    
    conditions = []
    if level: conditions.append(RequestLog.level == level)
    if status: conditions.append(RequestLog.status == status)
    if model: conditions.append(RequestLog.model.contains(model))
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            conditions.append(RequestLog.timestamp >= sd.replace(tzinfo=None))
        except: pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            conditions.append(RequestLog.timestamp <= ed.replace(tzinfo=None))
        except: pass
        
    if conditions:
        stmt = stmt.where(and_(*conditions))
        
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "Level", "Model", "Duration(ms)", "Status", "Prompt", "Error Details", "Stack Trace", "Retry Count"])
    
    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp.isoformat(),
            log.level,
            log.model,
            f"{log.duration_ms:.2f}",
            log.status,
            log.user_prompt_preview,
            log.full_response if log.status != 'success' else "",
            log.stack_trace or "",
            log.retry_count or 0
        ])
    
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=logs_export_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

@app.get("/api/stats", dependencies=[Depends(verify_gateway_key)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    # Today's stats
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total Requests Today
    q_total = select(func.count(RequestLog.id)).where(RequestLog.timestamp >= today)
    res_total = await db.execute(q_total)
    total_requests = res_total.scalar() or 0
    
    # Avg Duration Today
    q_avg = select(func.avg(RequestLog.duration_ms)).where(RequestLog.timestamp >= today)
    res_avg = await db.execute(q_avg)
    avg_duration = res_avg.scalar() or 0
    
    # Error Rate Today
    q_error = select(func.count(RequestLog.id)).where(
        RequestLog.timestamp >= today, 
        RequestLog.status != "success"
    )
    res_error = await db.execute(q_error)
    error_count = res_error.scalar() or 0
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
    
    # Intent Distribution (All time or Today? Let's do Today)
    q_intent = select(RequestLog.level, func.count(RequestLog.id)).where(RequestLog.timestamp >= today).group_by(RequestLog.level)
    res_intent = await db.execute(q_intent)
    intent_dist = [{"name": row[0], "value": row[1]} for row in res_intent.all()]
    
    # Recent Trend (Last 24h, grouped by hour) - Simplified to last 20 requests for now or simple daily stats
    # For chart "Response Time Trend", maybe last 50 requests?
    q_trend = select(RequestLog.timestamp, RequestLog.duration_ms).order_by(desc(RequestLog.timestamp)).limit(50)
    res_trend = await db.execute(q_trend)
    # Return ISO string for frontend to handle timezone
    trend_data = [{"time": row[0].isoformat(), "duration": row[1]} for row in res_trend.all()][::-1]

    return {
        "total_requests": total_requests,
        "avg_duration": round(avg_duration, 2),
        "error_rate": round(error_rate, 2),
        "intent_distribution": intent_dist,
        "response_trend": trend_data
    }

# --- Background Maintenance ---
# We can add a periodic task here or just expose an endpoint
@app.post("/api/maintenance/prune")
async def prune_logs_endpoint(days: int = 7, background_tasks: BackgroundTasks = None):
    if background_tasks:
        background_tasks.add_task(prune_logs, days)
    else:
        await prune_logs(days)
    return {"status": "started", "message": f"Pruning logs older than {days} days"}

# --- Static Files & SPA Fallback ---
# Check relative path to frontend/dist from backend/main.py
# Assuming structure:
# root/
#   backend/main.py
#   frontend/dist/

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API requests are already handled above due to precedence or explicit routes
        # But to be safe, we only serve index.html if it's NOT an API call
        if full_path.startswith("api/") or full_path.startswith("v1/"):
            raise HTTPException(status_code=404, detail="Not Found")
            
        # Serve index.html for all other routes (SPA)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to be accessible externally
    # Port changed to 6688 as requested
    uvicorn.run(app, host="0.0.0.0", port=6688)
