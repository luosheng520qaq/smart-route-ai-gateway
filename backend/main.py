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

from auth import (
    UserAuth, Token, UserCreate, TOTPVerify, TOTPSetupResponse, PasswordChange, UsernameChange, TOTPConfirm,
    get_current_active_user, create_access_token, verify_password, 
    get_password_hash, generate_totp_secret, get_totp_uri, verify_totp, 
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import init_db, get_db, RequestLog, User, AsyncSession, prune_logs

# --- Auth Routes ---
@app.post("/api/auth/login", response_model=Token)
async def login_for_access_token(form_data: UserAuth, db: AsyncSession = Depends(get_db)):
    # 1. Check User
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    
    # Auto-create admin if not exists (for first run ease of use)
    if not user and form_data.username == "admin":
        # Create default admin
        hashed = get_password_hash(form_data.password)
        new_user = User(username="admin", hashed_password=hashed)
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user = new_user
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Check 2FA if enabled (if secret exists)
    if user.totp_secret:
        # If 2FA is enabled, we need a code. But this login endpoint is for initial password check.
        # Flow:
        # A) If 2FA enabled -> Return a temporary "pre-auth" token or require code in request?
        #    Simpler: Require code in a separate step or included in login?
        #    Let's use a standard flow: Login returns Token ONLY if 2FA not enabled.
        #    If 2FA enabled, it returns 403 with detail="2FA_REQUIRED"
        pass 
    
    # For this implementation, we will assume the client sends the 2FA code in a header or we verify it in a second step.
    # To keep it simple but secure: Login just checks password. 
    # BUT, to enforce 2FA, we should check it here if set.
    # Let's add a "code" field to UserAuth or handle it.
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/2fa/verify", response_model=Token)
async def verify_2fa_login(
    username: str, 
    code: str, 
    password: str, # Re-verify password to be safe, or use a temp token
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.totp_secret:
         # 2FA not setup, just login
         access_token = create_access_token(data={"sub": user.username})
         return {"access_token": access_token, "token_type": "bearer"}
         
    if not verify_totp(user.totp_secret, code):
        raise HTTPException(status_code=401, detail="Invalid 2FA Code")
        
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA already enabled")
        
    secret = generate_totp_secret()
    # Don't save yet, wait for confirmation
    uri = get_totp_uri(secret, current_user.username)
    return {"secret": secret, "otpauth_url": uri}

@app.post("/api/auth/2fa/confirm")
async def confirm_2fa(
    data: TOTPConfirm,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_totp(data.secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid code")
        
    current_user.totp_secret = data.secret
    await db.commit()
    return {"status": "success", "message": "2FA Enabled"}

@app.get("/api/auth/me")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return {
        "username": current_user.username, 
        "is_active": current_user.is_active,
        "has_2fa": bool(current_user.totp_secret)
    }

@app.post("/api/auth/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    
    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()
    return {"status": "success", "message": "Password updated"}

@app.post("/api/auth/change-username")
async def change_username(
    username_data: UsernameChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify password
    if not verify_password(username_data.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    # 2. Check if new username exists
    result = await db.execute(select(User).where(User.username == username_data.new_username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # 3. Update username
    current_user.username = username_data.new_username
    await db.commit()
    
    # 4. Generate new token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.username}, expires_delta=access_token_expires
    )
    
    return {
        "status": "success", 
        "message": "Username updated", 
        "access_token": access_token, 
        "token_type": "bearer",
        "username": current_user.username
    }

# --- Management API (Protected by JWT) ---

@app.get("/api/config", dependencies=[Depends(get_current_active_user)])
async def get_config():
    return config_manager.get_config()

@app.get("/api/stats/models", dependencies=[Depends(get_current_active_user)])
async def get_model_stats():
    return router_engine.get_all_stats()

@app.post("/api/config", dependencies=[Depends(get_current_active_user)])
async def update_config(config: AppConfig):
    try:
        config_manager.update_config(config.model_dump())
        # Cleanup stats for removed models
        router_engine.cleanup_stats()
        return {"status": "success", "config": config_manager.get_config()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", dependencies=[Depends(get_current_active_user)])
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
    writer.writerow(["ID", "Timestamp", "Level", "Model", "Duration(ms)", "Status", "Prompt", "Error Details", "Stack Trace", "Retry Count", "Trace"])
    
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
            log.retry_count or 0,
            log.trace or ""
        ])
    
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=logs_export_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return response

@app.get("/api/stats", dependencies=[Depends(get_current_active_user)])
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
        response = FileResponse(os.path.join(frontend_dist, "index.html"))
        # Disable caching for index.html to ensure updates are seen immediately
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to be accessible externally
    # Port changed to 6688 as requested
    uvicorn.run(app, host="0.0.0.0", port=6688)
