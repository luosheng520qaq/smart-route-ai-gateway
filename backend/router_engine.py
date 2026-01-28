import httpx
import json
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel

from config_manager import config_manager
from database import AsyncSessionLocal, RequestLog

# Configure logging
logging.basicConfig(level=logging.INFO)
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
    async def determine_level(self, messages: List[Dict[str, Any]]) -> str:
        config = config_manager.get_config()
        
        # 1. Use Router Model if enabled
        if config.router_config.enabled:
            try:
                # Get last 3 user messages
                user_msgs = [m for m in messages if m.get("role") == "user"][-3:]
                history_text = "\n".join([f"User: {m.get('content', '')}" for m in user_msgs])
                
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
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"].strip().upper()
                        if "T1" in content: return "t1"
                        if "T2" in content: return "t2"
                        if "T3" in content: return "t3"
            except Exception as e:
                logger.error(f"Router Model failed: {e}. Falling back to heuristic.")

        # 2. Fallback Heuristic
        full_text = " ".join([m.get("content", "") or "" for m in messages])
        
        if len(full_text) > 2000:
            return "t3"
        
        complex_keywords = ["code", "function", "complex", "analysis", "summary", "reasoning"]
        if any(k in full_text.lower() for k in complex_keywords):
            return "t2"
            
        return "t1"

    async def route_request(self, request: ChatCompletionRequest, background_tasks: BackgroundTasks):
        start_time = time.time()
        config = config_manager.get_config()
        
        level = await self.determine_level(request.messages)
        
        models = []
        timeout_ms = 0
        
        if level == "t1":
            models = config.t1_models
            timeout_ms = config.timeouts.get("t1", 5000)
        elif level == "t2":
            models = config.t2_models
            timeout_ms = config.timeouts.get("t2", 15000)
        else: # t3
            models = config.t3_models
            timeout_ms = config.timeouts.get("t3", 30000)
            
        if not models:
            raise HTTPException(status_code=500, detail=f"No models configured for level {level}")

        last_error = None
        user_prompt = request.messages[-1].get("content", "") if request.messages else ""
        
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
                        # If provider not found, we might want to fail or just use default.
                        # Using default upstream but keeping full model_id might be wrong if it has prefix.
                        # Let's assume user meant to use default if provider alias not found? 
                        # Or maybe it's just a model name with slash.
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

                logger.info(f"Trying model {target_model_id} (Provider URL: {target_base_url}) for level {level}")
                response_data = await self._call_upstream(request, target_model_id, target_base_url, target_api_key, timeout_ms)
                
                # Log success (Async via BackgroundTasks)
                duration = (time.time() - start_time) * 1000
                background_tasks.add_task(
                    self._log_request,
                    level, target_model_id, duration, "success", user_prompt, request.model_dump_json(), json.dumps(response_data)
                )
                
                return response_data
            except Exception as e:
                logger.error(f"Model {model_id_entry} failed: {e}")
                last_error = e
                continue
                
        # All failed
        duration = (time.time() - start_time) * 1000
        background_tasks.add_task(
            self._log_request,
            level, "all", duration, "error", user_prompt, request.model_dump_json(), str(last_error)
        )
        raise HTTPException(status_code=502, detail=f"All models failed. Last error: {str(last_error)}")

    async def _call_upstream(self, request: ChatCompletionRequest, model_id: str, base_url: str, api_key: str, timeout_ms: int) -> Dict[str, Any]:
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
        
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            try:
                async with client.stream("POST", f"{base_url}/chat/completions", json=payload, headers=headers) as response:
                    
                    # 1. Check Status Code Failover
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_str = error_text.decode()
                        
                        should_retry = False
                        if response.status_code in config.retry_config.status_codes:
                            should_retry = True
                        
                        # 2. Check Error Keyword Failover
                        if not should_retry:
                            lower_error = error_str.lower()
                            if any(k in lower_error for k in config.retry_config.error_keywords):
                                should_retry = True
                        
                        if should_retry:
                            raise Exception(f"Retryable error {response.status_code}: {error_str}")
                        else:
                            raise Exception(f"Upstream error {response.status_code}: {error_str}")

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
                        raise Exception("Upstream returned empty content and no tool calls")

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
                    return final_response
            except httpx.ReadTimeout:
                raise Exception("Read timeout from upstream")
            except httpx.ConnectTimeout:
                raise Exception("Connect timeout to upstream")

    async def _log_request(self, level, model, duration, status, prompt, req_json, res_json):
        # This function is now run in background
        async with AsyncSessionLocal() as session:
            try:
                log_entry = RequestLog(
                    level=level,
                    model=model,
                    duration_ms=duration,
                    status=status,
                    user_prompt_preview=prompt[:200] if prompt else "",
                    full_request=req_json,
                    full_response=res_json
                )
                session.add(log_entry)
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to log request: {e}")

router_engine = RouterEngine()
