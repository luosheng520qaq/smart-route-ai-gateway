import httpx
import json
import time
import asyncio
import logging
import random
import uuid
import traceback
from typing import List, Dict, Any, Optional, Union
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel

from config_manager import config_manager
from database import AsyncSessionLocal, RequestLog
from logger import trace_logger

# Configure logging (Removed basicConfig as we use trace_logger now, but keeping logger for compatibility if needed)
logger = logging.getLogger("router")

class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None # Optional because we overwrite it
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

class RouterEngine:
    def _extract_text_from_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") in ["image_url", "image"]:
                        text_parts.append("[图片]")
            return "".join(text_parts)
        return str(content)

    async def determine_level(self, messages: List[Dict[str, Any]], trace_callback=None) -> str:
        config = config_manager.get_config()
        
        # Optimization: If the last message is from a tool, it means we are in a function calling loop.
        # Skip router model and default to T2 (Active/Tool-Use) if configured, else fallback gracefully.
        if messages and messages[-1].get("role") == "tool":
            logger.info("Tool response detected. Skipping router.")
            if config.t2_models:
                return "t2"
            elif config.t3_models:
                logger.info("T2 models empty, falling back to T3 for tool response.")
                return "t3"
            else:
                logger.warning("T2/T3 models empty, falling back to T1 for tool response (May fail if model weak).")
                return "t1"
        
        # 1. Use Router Model if enabled
        if config.router_config.enabled:
            try:
                # Log Router Start
                start_t = time.time()
                if trace_callback:
                    trace_callback("ROUTER_START", start_t, 0, "success", 0)

                # Get last 3 user messages
                user_msgs = [m for m in messages if m.get("role") == "user"][-3:]
                history_text = "\n".join([f"User: {self._extract_text_from_content(m.get('content'))}" for m in user_msgs])
                
                prompt = config.router_config.prompt_template.replace("{history}", history_text)
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        f"{config.router_config.base_url}/chat/completions",
                        json={
                            "model": config.router_config.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 10,
                            "temperature": 0.0
                        },
                        headers={"Authorization": f"Bearer {config.router_config.api_key}"}
                    )
                    
                    # Log Router End
                    end_t = time.time()
                    duration = (end_t - start_t) * 1000
                    if trace_callback:
                        trace_callback("ROUTER_END", end_t, duration, "success", 0)

                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"].strip().upper()
                        if "T1" in content: return "t1"
                        if "T2" in content: return "t2"
                        if "T3" in content: return "t3"
            except Exception as e:
                logger.error(f"Router Model failed: {e}. Falling back to heuristic.")
                # If Router enabled but failed, fall through to heuristic below
                if trace_callback:
                     trace_callback("ROUTER_FAIL", time.time(), 0, "fail", 0)
        else:
            # If Router disabled, use Random Level Selection as requested
            # Pick from levels that have models configured
            available_levels = []
            if config.t1_models: available_levels.append("t1")
            if config.t2_models: available_levels.append("t2")
            if config.t3_models: available_levels.append("t3")
            
            if available_levels:
                chosen = random.choice(available_levels)
                logger.info(f"Router disabled. Randomly selected level: {chosen}")
                return chosen
            return "t1" # Default fallback if no models configured

        # 2. Fallback Heuristic (Only used if Router enabled but failed)
        full_text = " ".join([self._extract_text_from_content(m.get("content")) for m in messages])
        
        if len(full_text) > 2000:
            return "t3"
        
        complex_keywords = ["code", "function", "complex", "analysis", "summary", "reasoning"]
        if any(k in full_text.lower() for k in complex_keywords):
            return "t2"
            
        return "t1"

    async def route_request(self, request: ChatCompletionRequest, background_tasks: BackgroundTasks):
        start_time = time.time() # Request Arrived (T0)
        trace_id = str(uuid.uuid4())
        
        trace_events = [] # List to store trace events for DB

        def add_trace_event(stage, abs_time, duration, st, rc, model=None, reason=None):
            event = {
                "stage": stage,
                "timestamp": abs_time,
                "duration_ms": duration,
                "status": st,
                "retry_count": rc
            }
            if model:
                event["model"] = model
            if reason:
                event["reason"] = reason
            trace_events.append(event)

        # 1. Log: Request Received
        trace_logger.log(trace_id, "REQ_RECEIVED", start_time, 0, "success")
        # Log REQ_RECEIVED for DB trace
        add_trace_event("REQ_RECEIVED", start_time, 0, "success", 0)
        
        config = config_manager.get_config()
        
        level = await self.determine_level(request.messages, trace_callback=add_trace_event)
        
        models = []
        timeout_ms = 0
        stream_timeout_ms = 0
        max_rounds = 1
        
        if level == "t1":
            models = config.t1_models
            timeout_ms = config.timeouts.get("t1", 5000)
            stream_timeout_ms = config.stream_timeouts.get("t1", 300000)
            max_rounds = config.retry_rounds.get("t1", 1)
        elif level == "t2":
            models = config.t2_models
            timeout_ms = config.timeouts.get("t2", 15000)
            stream_timeout_ms = config.stream_timeouts.get("t2", 300000)
            max_rounds = config.retry_rounds.get("t2", 1)
        else: # t3
            models = config.t3_models
            timeout_ms = config.timeouts.get("t3", 30000)
            stream_timeout_ms = config.stream_timeouts.get("t3", 300000)
            max_rounds = config.retry_rounds.get("t3", 1)
            
        if not models:
            raise HTTPException(status_code=500, detail=f"No models configured for level {level}")

        last_error = None
        last_stack_trace = None
        user_prompt = self._extract_text_from_content(request.messages[-1].get("content")) if request.messages else ""
        
        # Ensure max_rounds is at least 1
        if max_rounds < 1: max_rounds = 1
        
        retry_count = 0
        
        for round_idx in range(max_rounds):
            if round_idx > 0:
                logger.info(f"Starting Round {round_idx + 1}/{max_rounds} for level {level}")
                
            for model_id_entry in models:
                try:
                    # Resolve Provider
                    target_model_id = model_id_entry
                    target_base_url = config.upstream_base_url
                    target_api_key = config.upstream_api_key
                    
                    # 1. Check if model entry has "provider/model" format
                    if "/" in model_id_entry:
                        parts = model_id_entry.split("/", 1)
                        provider_id = parts[0]
                        real_model_id = parts[1]
                        
                        if provider_id in config.providers:
                            provider = config.providers[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_model_id = real_model_id
                        else:
                            logger.warning(f"Provider '{provider_id}' not found for model '{model_id_entry}'. Using default upstream.")
                            pass 

                    # 2. Check model_provider_map if no prefix used (or prefix resolution failed/ignored)
                    elif model_id_entry in config.model_provider_map:
                        provider_id = config.model_provider_map[model_id_entry]
                        if provider_id in config.providers:
                            provider = config.providers[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                        else:
                             logger.warning(f"Mapped provider '{provider_id}' not found for model '{model_id_entry}'. Using default upstream.")

                    # 2. Log: Model Call Start
                    call_start_time = time.time()
                    # Fix: Duration should be relative to previous step or just 0?
                    # The prompt says: "框架接收→首次调用"
                    # So duration_since_req is correct for "Framework Received -> First Call".
                    # BUT for subsequent calls (retries), it should be "Switch -> Retry".
                    # Let's check logic: call_start_time - start_time is "Time since Request Arrived".
                    # If this is a retry, start_time is still T0.
                    # User feedback says "delayed 900ms". Maybe because I was calculating since T0, but previous event was Router End?
                    # Ah, "Router End" happened at T+905ms. "Model Call Start" at T+906ms.
                    # The trace shows "duration_ms" for Model Call Start as +906ms.
                    # Frontend interprets this as "Duration of this stage"? Or "Time offset from start"?
                    # Frontend shows "+906ms" under Model Call Start.
                    # User asks why 900ms delay.
                    # Actually, if Frontend treats it as "Stage Duration", then "Router End" took 905ms?
                    # Wait, let's check Frontend logic.
                    # Frontend: +{event.duration_ms}ms.
                    # Backend: duration_since_req = (call_start_time - start_time) * 1000
                    # This means "Model Call Start" event records "Time elapsed since T0".
                    # This is correct for "Timestamp relative to start".
                    # But if the user thinks this is "Duration of the gap", then it is correct (gap is 906ms from start).
                    # User says: "Intent End at +905ms", "Model Start at +906ms".
                    # The gap is 1ms.
                    # Why user says "delayed 900ms"?
                    # User: "Intent End +905ms" ... "Model Start +906ms".
                    # Maybe user misread or the UI layout is confusing.
                    # Wait, user says: "Intent End... Model Start... +906ms".
                    # User asks: "Why delay 900ms?"
                    # Ah, "Intent End" took 900ms? No.
                    # Trace:
                    # 1. Intent Start (+0ms)
                    # 2. Intent End (+905ms) -> This means Intent Recognition took 905ms.
                    # 3. Model Start (+906ms) -> This means Model Start happened at 906ms from T0.
                    # So the gap between Intent End and Model Start is 1ms.
                    # User might be confusing "Duration of Stage" vs "Timestamp".
                    # Frontend shows "+906ms" which looks like timestamp offset.
                    
                    # BUT, look at "First Token +0ms".
                    # Code: trace_logger.log(trace_id, "FIRST_TOKEN", ttft_time, 0, ...)
                    # Here duration is hardcoded to 0!
                    # User says: "Model Call Start to First Token is 0ms, strange".
                    # Yes, because I hardcoded 0.
                    # Requirement d): "重试/首次调用→首包"耗时.
                    # So I should calculate (ttft_time - call_start_time).
                    
                    # Fix 1: Calculate TTFT duration correctly.
                    # Fix 2: User question about 900ms.
                    # If Intent End is +905ms, and Model Start is +906ms.
                    # The "Intent Recognition" stage took 905ms (http call to router model). This is normal.
                    # The "Model Call Start" timestamp is 906ms.
                    # User might be thinking "Model Call Start" itself took 906ms?
                    # No, "Model Call Start" is a point in time.
                    # I should ensure "duration" field in TraceEvent reflects "Stage Duration" or "Elapsed Time"?
                    # Requirement 2: "绝对时间(ms) | 阶段耗时(ms)"
                    # My add_trace_event usage:
                    # REQ_RECEIVED: duration=0
                    # ROUTER_END: duration=(end-start) -> 905ms. Correct.
                    # MODEL_CALL_START: duration=(call_start - start_time). This is "Elapsed since T0", NOT "Stage Duration".
                    # This is the bug!
                    # For point-in-time events (Start, First Token), "duration" should probably be:
                    # - For "Model Call Start": Duration of "Framework Prep"? Or just 0?
                    #   Req a): "发起→框架接收"耗时. (This is T0-ClientSend, we can't know ClientSend).
                    #   Req b): "框架接收→首次调用"耗时. This is (ModelCallStart - ReqReceived).
                    #   So for MODEL_CALL_START, duration should be (call_start_time - start_time).
                    #   Wait, if Router is involved, it includes Router time.
                    #   If Router is used: Req -> RouterStart -> RouterEnd -> ModelCallStart.
                    #   (ModelCallStart - RouterEnd) is the "Framework Prep" after routing.
                    #   (ModelCallStart - ReqReceived) is total prep time.
                    #   Current code: duration_since_req = (call_start_time - start_time).
                    #   This IS "Framework Prep" (including Router).
                    #   So +906ms is correct for "Time since Request Received".
                    
                    # User's confusion: "Intent End +905ms", "Model Start +906ms".
                    # User thinks "Model Start" implies *starting* the model call.
                    # User asks: "Why delayed 900ms?" -> Because Router took 905ms.
                    # User asks: "Model Start to First Token is 0ms?" -> Because I passed 0.
                    
                    # Fix Plan:
                    # 1. MODEL_CALL_START: duration should be "Time since Request Received" (as requested in 1b).
                    #    Current: (call_start - start_time). Correct.
                    # 2. FIRST_TOKEN: duration should be "Call Start -> First Token" (as requested in 1d).
                    #    Current: 0. Incorrect.
                    #    Fix: Pass (ttft_time - call_start_time).
                    
                    duration_since_req = (call_start_time - start_time) * 1000
                    trace_logger.log(trace_id, "MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count)
                    # For frontend consistency, we might want "Stage Duration" for everything?
                    # But the requirement says specific durations for specific events.
                    # Let's keep MODEL_CALL_START as "Time from T0".
                    add_trace_event("MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, model=target_model_id)
                    
                    logger.info(f"Trying model {target_model_id} (Provider URL: {target_base_url}) for level {level} (Round {round_idx + 1})")
                    
                    # Pass callback or wrapper to capture internal events if needed, or just return them
                    # Actually _call_upstream needs to return timing info or we pass a mutable object
                    # Let's pass trace_events list to _call_upstream? No, it's better to keep it clean.
                    # _call_upstream already logs to trace_logger. 
                    # We need to capture those times for DB too.
                    # Let's modify _call_upstream to return metadata along with response?
                    # Or pass the add_trace_event callback.
                    
                    response_data = await self._call_upstream(request, target_model_id, target_base_url, target_api_key, timeout_ms, stream_timeout_ms, trace_id, retry_count, call_start_time, add_trace_event)
                    
                    # 3. Log: Full Response (Success)
                    end_time = time.time()
                    duration = (end_time - start_time) * 1000
                    
                    # Log success (Async via BackgroundTasks)
                    background_tasks.add_task(
                        self._log_request,
                        level, target_model_id, duration, "success", user_prompt, request.model_dump_json(), json.dumps(response_data), trace_events
                    )
                    
                    return response_data
                except Exception as e:
                    # 4. Log: Retry/Fail
                    fail_time = time.time()
                    fail_duration = (fail_time - call_start_time) * 1000
                    
                    # Extract Reason from Exception
                    error_msg = str(e)
                    reason = "Unknown Error"
                    if "TTFT Timeout" in error_msg:
                        reason = "超首token限制时长"
                    elif "Total Timeout" in error_msg:
                        reason = "超总限制时长"
                    elif "Status Code Error" in error_msg:
                         # Extract code?
                         reason = "触发错误状态码"
                         if ":" in error_msg:
                             reason += f": {error_msg.split(':')[1].strip()}"
                    elif "Error Keyword Match" in error_msg:
                         reason = "错误关键词"
                         if ":" in error_msg:
                             reason += f": {error_msg.split(':')[1].strip()}"
                    elif "Empty Response" in error_msg:
                        reason = "空返回"
                    elif "Connect Timeout" in error_msg:
                        reason = "连接超时"
                    elif "Upstream Error" in error_msg:
                         reason = "上游错误"
                         if ":" in error_msg:
                             reason += f": {error_msg.split(':')[1].strip()}"
                    else:
                        reason = error_msg[:50] # Fallback to first 50 chars

                    trace_logger.log(trace_id, "MODEL_FAIL", fail_time, fail_duration, "fail", retry_count)
                    add_trace_event("MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, model=target_model_id, reason=reason)
                    
                    logger.error(f"Model {model_id_entry} failed (Round {round_idx + 1}): {e}")
                    last_error = e
                    last_stack_trace = traceback.format_exc()
                    retry_count += 1
                    continue
                
        # All failed
        duration = (time.time() - start_time) * 1000
        trace_logger.log(trace_id, "ALL_FAILED", time.time(), duration, "fail", retry_count)
        add_trace_event("ALL_FAILED", time.time(), duration, "fail", retry_count)
        
        background_tasks.add_task(
            self._log_request,
            level, "all", duration, "error", user_prompt, request.model_dump_json(), str(last_error), trace_events, last_stack_trace, retry_count
        )
        raise HTTPException(status_code=502, detail=f"All models failed. Last error: {str(last_error)}")

    async def _call_upstream(self, request: ChatCompletionRequest, model_id: str, base_url: str, api_key: str, timeout_ms: int, stream_timeout_ms: int, trace_id: str, retry_count: int, req_start_time: float, trace_callback=None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare payload
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model_id
        payload["stream"] = True # Force stream for aggregation
        
        config = config_manager.get_config()
        
        # --- Parameter Merge Logic ---
        # Priority: Request > Model Specific > Global Default
        
        # 1. Global Defaults
        for key, value in config.global_params.items():
            if key not in payload:
                payload[key] = value
                
        # 2. Model Specific Defaults
        if model_id in config.model_params:
            for key, value in config.model_params[model_id].items():
                if key not in payload or request.model_dump().get(key) is None: 
                    # Note: We use request.model_dump().get(key) is None to check if user explicitly set it.
                    # But payload was created with exclude_none=True, so if it's not in payload, it was None.
                    # However, we just added global params to payload.
                    # So we should check if the key was originally in the request?
                    # Actually, simply overwriting if it was NOT in the original request is the right logic.
                    # But wait, payload currently contains Request params (if not None) + Global params (if not in Request).
                    # If Model param exists, it should override Global param, but NOT Request param.
                    
                    # Let's refine:
                    # Start with Global Params
                    # Update with Model Params
                    # Update with Request Params (that are not None)
                    pass

        # Re-construct payload to ensure correct precedence
        final_payload = {}
        
        # Base: Global Defaults
        final_payload.update(config.global_params)
        
        # Override: Model Specific Defaults
        if model_id in config.model_params:
            final_payload.update(config.model_params[model_id])
            
        # Override: Request Params (only if not None)
        request_dict = request.model_dump(exclude_none=True)
        final_payload.update(request_dict)
        
        # Ensure critical fields
        final_payload["model"] = model_id
        final_payload["stream"] = True
        
        payload = final_payload
        # -----------------------------
        
        timeout_sec = timeout_ms / 1000.0
        # Use user-configured timeout for the stream continuity
        stream_timeout = stream_timeout_ms / 1000.0
        
        # Configure granular timeouts
        # connect: fail fast if upstream is unreachable (capped at TTFT timeout)
        # read: allow long generation (capped at Stream timeout)
        timeout_config = httpx.Timeout(
            connect=timeout_sec,
            read=stream_timeout,
            write=stream_timeout,
            pool=stream_timeout
        )
        
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                # Manually manage the stream context to decouple TTFT timeout from Body timeout
                ctx = client.stream("POST", f"{base_url}/chat/completions", json=payload, headers=headers)
                
                try:
                    # Enforce TTFT (Wait for Headers)
                    # Note: httpx connect timeout will trigger first/simultaneously if connection fails
                    response = await asyncio.wait_for(ctx.__aenter__(), timeout=timeout_sec)
                except asyncio.TimeoutError:
                    raise Exception(f"TTFT Timeout (Headers) > {timeout_sec}s")
                except Exception:
                    raise
                
                # 3. Log: First Token (Headers Received)
                ttft_time = time.time()
                # Duration from "Request Received" (or "Retry Start"?) Prompt says: "Retry/FirstCall -> First Token"
                # So we need time of THIS call start? Yes, req_start_time passed in is actually call_start_time now.
                duration_ttft = (ttft_time - req_start_time) * 1000
                
                trace_logger.log(trace_id, "FIRST_TOKEN", ttft_time, duration_ttft, "success", retry_count)
                if trace_callback:
                    trace_callback("FIRST_TOKEN", ttft_time, duration_ttft, "success", retry_count) 

                try:
                    # 1. Check Status Code Failover
                    if response.status_code != 200:
                        try:
                            error_text = await asyncio.wait_for(response.aread(), timeout=10.0)
                        except asyncio.TimeoutError:
                            error_text = b"Error body read timed out"
                            
                        error_str = error_text.decode(errors='replace')
                        
                        should_retry = False
                        if response.status_code in config.retry_config.status_codes:
                            should_retry = True
                        
                        # 2. Check Error Keyword Failover
                        keyword_match = None
                        if not should_retry:
                            lower_error = error_str.lower()
                            for k in config.retry_config.error_keywords:
                                if k in lower_error:
                                    should_retry = True
                                    keyword_match = k
                                    break
                        
                        if should_retry:
                            if keyword_match:
                                raise Exception(f"Error Keyword Match: {keyword_match} in {error_str[:100]}")
                            else:
                                raise Exception(f"Status Code Error: {response.status_code} - {error_str[:100]}")
                        else:
                            raise Exception(f"Upstream Error: {response.status_code} - {error_str[:100]}")

                    # Aggregate Stream
                    aggregated_content = ""
                    aggregated_tool_calls = {} # index -> tool_call
                    finish_reason = None
                    role = "assistant"
                    
                    # Fix for Kimi/Moonshot & httpx compatibility issues:
                    # Manually handle buffer and decoding instead of relying on aiter_lines()
                    buffer = ""
                    async for chunk in response.aiter_bytes():
                        try:
                            text_chunk = chunk.decode("utf-8")
                        except UnicodeDecodeError:
                            # Handle potential split multi-byte characters if needed, 
                            # but for now assume clean chunks or use 'ignore/replace' if critical.
                            # For robustness, we could use an incremental decoder, but let's try simple first.
                            text_chunk = chunk.decode("utf-8", errors="replace")
                            
                        buffer += text_chunk
                        
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            
                            if not line:
                                continue
                                
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    continue # Don't break yet, process rest of buffer
                                try:
                                    chunk_json = json.loads(data_str)
                                    choices = chunk_json.get("choices", [])
                                    if not choices:
                                        continue
                                        
                                    delta = choices[0].get("delta", {})
                                    finish_reason = choices[0].get("finish_reason", finish_reason)
                                    
                                    # Aggregate Content
                                    if "content" in delta and delta["content"] is not None:
                                        aggregated_content += delta["content"]
                                        
                                    # Aggregate Tool Calls
                                    if "tool_calls" in delta and delta["tool_calls"]:
                                        for tc in delta["tool_calls"]:
                                            index = tc.get("index")
                                            if index not in aggregated_tool_calls:
                                                aggregated_tool_calls[index] = {
                                                    "id": tc.get("id", ""),
                                                    "type": tc.get("type", "function"),
                                                    "function": {"name": "", "arguments": ""}
                                                }
                                            
                                            if tc.get("id"):
                                                aggregated_tool_calls[index]["id"] = tc["id"]
                                            
                                            if "function" in tc:
                                                if tc["function"].get("name"):
                                                    aggregated_tool_calls[index]["function"]["name"] += tc["function"]["name"]
                                                if tc["function"].get("arguments"):
                                                    aggregated_tool_calls[index]["function"]["arguments"] += tc["function"]["arguments"]

                                except json.JSONDecodeError:
                                    continue

                    # Check for empty content (Retry trigger)
                    if not aggregated_content and not aggregated_tool_calls:
                        raise Exception("Empty Response: Upstream returned empty content and no tool calls")

                    # Construct final response
                    message = {
                        "role": role,
                        "content": aggregated_content if aggregated_content else None
                    }
                    
                    if aggregated_tool_calls:
                        tool_calls_list = []
                        for i in sorted(aggregated_tool_calls.keys()):
                            tool_calls_list.append(aggregated_tool_calls[i])
                        message["tool_calls"] = tool_calls_list
                    
                    final_response = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model_id,
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": finish_reason or "stop"
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 0, # Difficult to calculate without tokenizer
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }
                    }
                    
                    # 5. Log: Full Response
                    full_resp_time = time.time()
                    # Duration from First Token -> Full Return
                    duration_since_ttft = (full_resp_time - ttft_time)*1000
                    trace_logger.log(trace_id, "FULL_RESPONSE", full_resp_time, duration_since_ttft, "success", retry_count)
                    if trace_callback:
                        trace_callback("FULL_RESPONSE", full_resp_time, duration_since_ttft, "success", retry_count)
                    
                    return final_response
                except Exception as e:
                     # Propagate exception to context manager
                     if not await ctx.__aexit__(type(e), e, e.__traceback__):
                         raise
                else:
                     # Success exit
                     await ctx.__aexit__(None, None, None)

            except httpx.ReadTimeout:
                raise Exception("Total Timeout (Read): Read timeout from upstream")
            except httpx.ConnectTimeout:
                raise Exception("Connect Timeout: Connect timeout to upstream")

    async def _log_request(self, level, model, duration, status, prompt, req_json, res_json, trace_data=None, stack_trace=None, retry_count=0):
        # This function is now run in background
        async with AsyncSessionLocal() as session:
            try:
                # Optimize Logging: Extract only necessary info
                
                # 1. Request: Only user messages
                clean_req = "Check user_prompt_preview"
                try:
                    req_obj = json.loads(req_json)
                    # Extract last user message or system instruction? User said "record user input".
                    # Let's extract all messages but keep them minimal (content only)
                    if "messages" in req_obj and req_obj["messages"]:
                         # Only keep the last message to save space (Current Request)
                         last_msg = req_obj["messages"][-1]
                         clean_req = json.dumps([{
                             "role": last_msg.get("role"), 
                             "content": self._extract_text_from_content(last_msg.get("content"))
                         }], ensure_ascii=False)
                except:
                    clean_req = req_json # Fallback

                # 2. Response: Only assistant content or tool calls
                clean_res = "Empty"
                try:
                    res_obj = json.loads(res_json)
                    if "choices" in res_obj and len(res_obj["choices"]) > 0:
                        message = res_obj["choices"][0].get("message", {})
                        content = message.get("content")
                        tool_calls = message.get("tool_calls")
                        
                        log_data = {}
                        if content:
                            log_data["content"] = content
                        if tool_calls:
                            log_data["tool_calls"] = tool_calls
                            
                        clean_res = json.dumps(log_data, ensure_ascii=False)
                    elif "error" in res_obj:
                        clean_res = json.dumps(res_obj["error"], ensure_ascii=False)
                except:
                    clean_res = res_json # Fallback

                log_entry = RequestLog(
                    level=level,
                    model=model,
                    duration_ms=duration,
                    status=status,
                    user_prompt_preview=prompt[:200] if prompt else "",
                    full_request=clean_req,
                    full_response=clean_res,
                    trace=json.dumps(trace_data) if trace_data else None,
                    stack_trace=stack_trace,
                    retry_count=retry_count
                )
                session.add(log_entry)
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to log request: {e}")

router_engine = RouterEngine()
