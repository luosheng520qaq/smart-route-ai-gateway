
import logging
import sys
import json
import uuid
from datetime import datetime
from collections import deque
from fastapi import WebSocket, WebSocketDisconnect
from typing import List

# --- Log Format & Buffer ---

class TraceLogger:
    def __init__(self):
        self.buffer = deque(maxlen=10000) # Ring buffer 10k lines
        self.active_websockets: List[WebSocket] = []
        
        # Configure stdout logger
        self.logger = logging.getLogger("smart_route_trace")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

    def _format_log(self, trace_id: str, stage: str, start_time: float, duration_ms: float, status: str, retry_count: int = 0):
        # Format: [ISO-8601] | traceId | Stage | AbsTime(ms) | Duration(ms) | Status | RetryCount
        iso_time = datetime.utcnow().isoformat() + "Z"
        abs_time_ms = int(start_time * 1000)
        
        log_msg = f"[{iso_time}] | {trace_id} | {stage} | {abs_time_ms} | {duration_ms:.2f} | {status}"
        if retry_count > 0:
            log_msg += f" | retry={retry_count}"
            
        return log_msg

    def log(self, trace_id: str, stage: str, start_time: float, duration_ms: float, status: str, retry_count: int = 0):
        msg = self._format_log(trace_id, stage, start_time, duration_ms, status, retry_count)
        
        # 1. Print to Stdout
        self.logger.info(msg)
        
        # 2. Add to Buffer
        self.buffer.append(msg)
        
        # 3. Broadcast to WebSockets
        self.broadcast(msg)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)
        # Send last 1000 lines on connect
        history = list(self.buffer)[-1000:]
        try:
            for line in history:
                await websocket.send_text(line)
        except:
            pass # Disconnect handled in loop

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    def broadcast(self, message: str):
        # Fire and forget (sync wrapper for async broadcast is tricky in non-async log calls)
        # However, FastAPI runs in async loop. We can use asyncio.create_task if we have loop access.
        # But logging might happen in sync context? 
        # Actually our router is async, so we can await or create task.
        # For simplicity, we'll store msg and let a background task flush, or iterate directly if active_websockets is thread-safe enough (it's not).
        # Better: Since our core logic is async, let's make a async broadcast or use a queue.
        # But to keep it simple and given performance reqs (<200ms), direct send is risky if clients slow.
        # We will use a naive loop here, assuming standard usage.
        import asyncio
        # Check if there's a running loop
        try:
            loop = asyncio.get_running_loop()
            for ws in self.active_websockets:
                loop.create_task(self._safe_send(ws, message))
        except RuntimeError:
            pass # No loop

    async def _safe_send(self, ws: WebSocket, msg: str):
        try:
            await ws.send_text(msg)
        except:
            self.disconnect(ws)

trace_logger = TraceLogger()
