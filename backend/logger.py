
import logging
import sys
import json
import uuid
from datetime import datetime
from collections import deque
from fastapi import WebSocket, WebSocketDisconnect
from typing import List

# --- Log Format & Buffer ---

STAGE_MAPPING = {
    "REQ_RECEIVED": "收到请求",
    "MODEL_CALL_START": "开始调用模型",
    "FIRST_TOKEN": "首字返回",
    "FULL_RESPONSE": "响应完成",
    "MODEL_FAIL": "模型调用失败",
    "ALL_FAILED": "全部尝试失败",
    "ROUTER_FAIL": "路由决策失败"
}

STATUS_MAPPING = {
    "success": "成功",
    "fail": "失败",
    "error": "错误"
}

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

    def _format_log(self, trace_id: str, stage: str, start_time: float, duration_ms: float, status: str, retry_count: int = 0, details: str = ""):
        # Format: [Time] [Stage] Status (Duration) | Details
        # Chinese friendly format
        local_time = datetime.fromtimestamp(start_time).strftime('%H:%M:%S.%f')[:-3]
        
        stage_cn = STAGE_MAPPING.get(stage, stage)
        status_cn = STATUS_MAPPING.get(status, status)
        
        # Color/Icon simulation for text log (Frontend can parse this or we just send text)
        # Let's keep it structured text
        
        log_msg = f"[{local_time}] 【{stage_cn}】 {status_cn}"
        
        if duration_ms > 0:
            log_msg += f" (耗时: {duration_ms:.2f}ms)"
            
        if retry_count > 0:
            log_msg += f" [重试: {retry_count}]"
            
        if details:
            log_msg += f" | {details}"
            
        # Append raw trace_id for debugging if needed, maybe shorter?
        log_msg += f" <{trace_id[:8]}>"
            
        return log_msg

    def log(self, trace_id: str, stage: str, start_time: float, duration_ms: float, status: str, retry_count: int = 0, details: str = ""):
        msg = self._format_log(trace_id, stage, start_time, duration_ms, status, retry_count, details)
        
        # 1. Print to Stdout
        self.logger.info(msg)
        
        # 2. Add to Buffer
        self.buffer.append(msg)
        
        # 3. Broadcast to WebSockets
        self.broadcast(msg)

    def log_separator(self, char="-", length=60):
        msg = char * length
        self.logger.info(msg)
        self.buffer.append(msg)
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
