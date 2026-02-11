import httpx
import json
import time
import asyncio
import logging
import random
import uuid
import traceback
import os
import re
try:
    import tiktoken
except ImportError:
    tiktoken = None

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
    _client: Optional[httpx.AsyncClient] = None
    _model_stats: Dict[str, Dict[str, Any]] = {} # { "model_id": { "failures": 0.0, "success": 0, "last_updated": timestamp } }
    _stats_file: str = "model_stats.json"
    _tokenizer = None

    def _get_tokenizer(self, model: str):
        if self._tokenizer: return self._tokenizer
        if tiktoken:
            try:
                # Try to get specific encoding, default to cl100k_base (gpt-4/3.5)
                self._tokenizer = tiktoken.encoding_for_model(model)
            except:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
        return self._tokenizer

    def _count_tokens(self, text: str, model: str = "gpt-3.5-turbo") -> int:
        if not text: return 0
        tokenizer = self._get_tokenizer(model)
        if tokenizer:
            return len(tokenizer.encode(text))
        else:
            # Fallback: Approx 4 chars per token
            return len(text) // 4

    def _count_messages_tokens(self, messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo") -> int:
        """
        Count tokens for a list of messages (Chat format).
        Follows OpenAI logic: 3 tokens overhead per message + tokens in content.
        """
        tokenizer = self._get_tokenizer(model)
        if not tokenizer:
            # Fallback: Sum chars of content + role
            total_chars = sum(len(str(m.get("content", ""))) + len(str(m.get("role", ""))) for m in messages)
            return total_chars // 4
        
        num_tokens = 0
        for message in messages:
            num_tokens += 3  # <|start|>{role/name}\n{content}<|end|>\n
            for key, value in message.items():
                if key == "content" and isinstance(value, str):
                    num_tokens += len(tokenizer.encode(value))
                elif key == "name":
                    num_tokens += 1
                # Ignore other keys or handle multimodal content later
        
        num_tokens += 3  # <|start|>assistant<|message|>
        return num_tokens

    async def startup(self):
        """Initialize global HTTP client and model stats"""
        if self._client is None:
            # Configure global pool limits
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
            self._client = httpx.AsyncClient(limits=limits)
            logger.info("Global HTTP Client initialized")
        
        # Load stats from disk
        self._load_stats()
        
        # Pre-populate stats for all configured models (if not in file)
        config = config_manager.get_config()
        all_models = set(config.models.t1 + config.models.t2 + config.models.t3)
        for m in all_models:
            if m and m not in self._model_stats:
                self._model_stats[m] = {
                    "failures": 0.0, 
                    "success": 0, 
                    "last_updated": time.time()
                }

    async def shutdown(self):
        """Close global HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Global HTTP Client closed")
        # Save stats to disk
        self._save_stats()

    def _load_stats(self):
        if os.path.exists(self._stats_file):
            try:
                with open(self._stats_file, 'r', encoding='utf-8') as f:
                    self._model_stats = json.load(f)
                logger.info("Model stats loaded from disk")
            except Exception as e:
                logger.error(f"Failed to load model stats: {e}")
                self._model_stats = {}

    def _save_stats(self):
        try:
            with open(self._stats_file, 'w', encoding='utf-8') as f:
                json.dump(self._model_stats, f, indent=2)
            logger.info("Model stats saved to disk")
        except Exception as e:
            logger.error(f"Failed to save model stats: {e}")

    def _get_model_stats(self, model_id: str) -> Dict[str, Any]:
        if model_id not in self._model_stats:
            self._model_stats[model_id] = {
                "failures": 0, 
                "success": 0, 
                "failure_score": 0.0, 
                "cooldown_until": 0,
                "last_updated": time.time()
            }
        
        # Backward compatibility / Migration
        stats = self._model_stats[model_id]
        if "failure_score" not in stats:
            # Migration: Use existing failures as score, but cast failures to int
            current_val = stats.get("failures", 0.0)
            stats["failure_score"] = float(current_val)
            stats["failures"] = int(current_val)

        if "last_updated" not in stats:
            stats["last_updated"] = time.time()
            
        # Calculate dynamic health score (0-100) for UI
        # If cooldown is active, show 0 health
        if stats.get("cooldown_until", 0) > time.time():
            stats["health_score"] = 0
        else:
            fs = stats.get("failure_score", 0.0)
            stats["health_score"] = int(100.0 / (1.0 + fs * 0.2))
            
        return stats

    def _refresh_stats(self, model_id: str):
        """Apply time-based decay to failure_score to allow automatic recovery."""
        stats = self._get_model_stats(model_id)
        now = time.time()
        last_updated = stats.get("last_updated", now)
        
        # Decay Configuration from ConfigManager
        config = config_manager.get_config()
        decay_rate = config.health.decay_rate
        
        # Recover decay_rate points per minute
        elapsed_min = (now - last_updated) / 60.0
        
        if elapsed_min > 0.1: # Only update if meaningful time passed (>6s)
            decay_amount = elapsed_min * decay_rate
            if stats["failure_score"] > 0:
                stats["failure_score"] = max(0.0, stats["failure_score"] - decay_amount)
            
            stats["last_updated"] = now

    def _record_success(self, model_id: str):
        self._refresh_stats(model_id) # Apply decay first
        stats = self._get_model_stats(model_id)
        stats["success"] += 1
        stats["cooldown_until"] = 0 # Clear cooldown on success
        
        # Significant bonus on success: reduce failure score by 2.0
        if stats["failure_score"] > 0:
            stats["failure_score"] = max(0.0, stats["failure_score"] - 2.0)
            
        stats["last_updated"] = time.time()
        self._save_stats() # Persist on change (optimize frequency if high traffic)

    def _record_failure(self, model_id: str, penalty: float = 1.0, cooldown_seconds: int = 0):
        self._refresh_stats(model_id) # Apply decay first
        stats = self._get_model_stats(model_id)
        stats["failures"] += 1 # Integer counter (always increments)
        stats["failure_score"] += penalty # Dynamic score (decays)
        
        if cooldown_seconds > 0:
            stats["cooldown_until"] = time.time() + cooldown_seconds
            
        stats["last_updated"] = time.time()
        self._save_stats() # Persist on change

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        # Refresh all stats before returning to UI
        for m in list(self._model_stats.keys()):
            self._refresh_stats(m)
        return self._model_stats

    def cleanup_stats(self):
        """Remove stats for models that are no longer in the configuration"""
        config = config_manager.get_config()
        current_models = set(config.models.t1 + config.models.t2 + config.models.t3)
        
        # Identify keys to remove (to avoid modifying dict while iterating)
        to_remove = [m for m in self._model_stats if m not in current_models]
        
        for m in to_remove:
            del self._model_stats[m]
            logger.info(f"Removed stats for deleted model: {m}")
        
        # Also ensure new models are initialized
        for m in current_models:
            if m and m not in self._model_stats:
                self._model_stats[m] = {
                    "failures": 0, 
                    "success": 0, 
                    "failure_score": 0.0, 
                    "last_updated": time.time()
                }
        
        self._save_stats() # Persist after cleanup

    def _get_sorted_models(self, models: List[str], strategy: str) -> List[str]:
        if not models:
            return []
            
        if strategy == "sequential":
            return models
            
        if strategy == "random":
            # Pure random shuffle
            shuffled = list(models)
            random.shuffle(shuffled)
            return shuffled
            
        if strategy == "adaptive":
            # Weighted random based on failures
            # Refined Algorithm: Weight = 1 / (1 + failure_score * 0.5)
            # This makes the decay less aggressive. 
            # 1 failure -> 1/1.2 = 0.83 (was 0.5)
            # 5 failures -> 1/2.0 = 0.50 (was 0.16)
            # 10 failures -> 1/3.0 = 0.33 (was 0.09)
            
            scored_models = []
            for m in models:
                # Refresh stats first to apply time decay
                self._refresh_stats(m)
                stats = self._get_model_stats(m)
                
                weight = 1.0 / (1.0 + stats["failure_score"] * 0.5) # Increased sensitivity slightly (0.2 -> 0.5) since failures decay now
                
                # Probabilistic score: higher weight increases chance of higher score
                score = random.random() * weight
                scored_models.append((score, m))
            
            # Sort desc by score
            scored_models.sort(key=lambda x: x[0], reverse=True)
            return [m for _, m in scored_models]
            
        return models

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

    def _convert_to_anthropic_messages(self, openai_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert OpenAI message format to Anthropic format.
        Returns a dict with 'system' (str) and 'messages' (list).
        """
        anthropic_messages = []
        system_prompt = None
        
        # Buffer for consecutive tool outputs to merge into one User message
        tool_results_buffer = []
        
        def flush_tool_buffer():
            nonlocal tool_results_buffer
            if tool_results_buffer:
                # Anthropic expects tool results to be USER messages
                # But we should verify if the LAST message was a User message to merge?
                # No, Anthropic documentation says:
                # "Tool result messages should be alternating with Assistant messages"
                # Actually, in the Messages API:
                # User (with tool_result content) -> Assistant -> User...
                # So if we have multiple tool results, they should be in ONE User message block.
                # However, if the previous message was ALSO a User message (text), 
                # we might need to merge them if Anthropic doesn't allow consecutive User messages.
                # BUT: The standard flow is User -> Assistant(ToolUse) -> User(ToolResult).
                # So the previous message MUST be Assistant.
                # If we have consecutive Tool Results (parallel tools), they go into ONE User msg.
                
                # Check if the last message in anthropic_messages is a User message
                if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                    # Merge into existing user message
                    current_content = anthropic_messages[-1]["content"]
                    if isinstance(current_content, list):
                        current_content.extend(tool_results_buffer)
                    elif isinstance(current_content, str):
                        # Convert string content to list structure
                        new_content = [{"type": "text", "text": current_content}]
                        new_content.extend(tool_results_buffer)
                        anthropic_messages[-1]["content"] = new_content
                else:
                    # Create new user message
                    anthropic_messages.append({
                        "role": "user",
                        "content": tool_results_buffer
                    })
                tool_results_buffer = []

        for msg in openai_messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                # Extract system prompt
                # Anthropic supports only one system prompt usually, or we join them?
                # Using the last one or joining is common practice. Let's join if multiple.
                text_content = self._extract_text_from_content(content)
                if system_prompt:
                    system_prompt += "\n" + text_content
                else:
                    system_prompt = text_content
                continue
            
            # If we encounter a non-tool message, flush any pending tool results
            if role != "tool":
                flush_tool_buffer()

            if role == "user":
                # Check if previous message was also user, if so merge (Anthropic doesn't like consecutive User messages)
                if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                     # Merge text content
                     prev_content = anthropic_messages[-1]["content"]
                     new_text = self._extract_text_from_content(content)
                     
                     if isinstance(prev_content, str):
                         anthropic_messages[-1]["content"] = prev_content + "\n" + new_text
                     elif isinstance(prev_content, list):
                         prev_content.append({
                             "type": "text",
                             "text": new_text
                         })
                else:
                    anthropic_messages.append({
                        "role": "user",
                        "content": content
                    })
            
            elif role == "assistant":
                # Handle tool_calls conversion
                tool_calls = msg.get("tool_calls")
                new_content = []
                
                # 1. Text Content
                if content:
                    new_content.append({
                        "type": "text",
                        "text": content
                    })
                
                # 2. Tool Uses
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        args_str = func.get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                        except:
                            args = {}
                            
                        new_content.append({
                            "type": "tool_use",
                            "id": tc.get("id"),
                            "name": func.get("name"),
                            "input": args
                        })
                
                anthropic_messages.append({
                    "role": "assistant",
                    "content": new_content
                })
            
            elif role == "tool":
                # Convert to tool_result block and buffer it
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id"),
                    "content": self._extract_text_from_content(content)
                }
                # Handle error state? OpenAI doesn't explicitly have error in tool msg, 
                # but sometimes content implies error. Anthropic has is_error field.
                # For now, keep simple.
                tool_results_buffer.append(tool_result)
        
        # Final flush
        flush_tool_buffer()
        
        return {
            "system": system_prompt,
            "messages": anthropic_messages
        }

    async def determine_level(self, messages: List[Dict[str, Any]], trace_callback=None) -> str:
        config = config_manager.get_config()
        
        # Optimization: If the last message is from a tool, it means we are in a function calling loop.
        # Skip router model and default to T2 (Active/Tool-Use) if configured, else fallback gracefully.
        if messages and messages[-1].get("role") == "tool":
            logger.info("Tool response detected. Skipping router.")
            if config.models.t2:
                return "t2"
            elif config.models.t3:
                logger.info("T2 models empty, falling back to T3 for tool response.")
                return "t3"
            else:
                logger.warning("T2/T3 models empty, falling back to T1 for tool response (May fail if model weak).")
                return "t1"
        
        # 1. Use Router Model if enabled
        if config.router.enabled:
            try:
                # Log Router Start
                start_t = time.time()
                if trace_callback:
                    trace_callback("ROUTER_START", start_t, 0, "success", 0)

                # Get recent user context (last 3 user messages)
                # Filter for user messages only as requested to avoid token overflow
                user_msgs = [m for m in messages if m.get("role") == "user"][-3:]
                history_lines = []
                for m in user_msgs:
                    content = self._extract_text_from_content(m.get("content"))
                    # Truncate very long messages
                    if len(content) > 800:
                        content = content[:800] + "...(truncated)"
                    history_lines.append(f"User: {content}")
                history_text = "\n".join(history_lines)
                
                prompt = config.router.prompt_template.replace("{history}", history_text)
                
                # Use global client if available, else create one
                if self._client is None: await self.startup()
                
                # Note: self._client has global limits, but we need specific timeout here.
                # request-level timeout overrides client timeout.
                # Verify SSL based on router config
                verify_ssl = getattr(config.router, "verify_ssl", True)
                
                resp = await self._client.post(
                    f"{config.router.base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": config.router.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 10,
                        "temperature": 0.0
                    },
                    headers={"Authorization": f"Bearer {config.router.api_key}"},
                    timeout=5.0,
                    # Disable verify if configured (e.g. self-signed certs)
                    verify=verify_ssl
                )
                    
            # Log Router End
                end_t = time.time()
                duration = (end_t - start_t) * 1000
                if trace_callback:
                    trace_callback("ROUTER_END", end_t, duration, "success", 0)

                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"].strip().upper()
                    # Use Regex to find standalone T1/T2/T3 to avoid partial matches
                    match = re.search(r'\bT([1-3])\b', content)
                    if match: 
                        return f"t{match.group(1)}"
                    
                    # Fallback simple check if regex fails
                    if "T1" in content: return "t1"
                    if "T2" in content: return "t2"
                    if "T3" in content: return "t3"
            except Exception as e:
                logger.error(f"Router Model failed: {e}. Falling back to heuristic.")
                # If Router enabled but failed, fall through to heuristic below
                if trace_callback:
                     trace_callback("ROUTER_FAIL", time.time(), 0, "fail", 0)
        else:
            # If Router disabled, as requested by user, we default to T1 only.
            # This allows T1 to act as a fault-tolerant/fallback pool.
            logger.info("Router disabled. Defaulting to T1 level for fault tolerance.")
            return "t1"

        # 2. Fallback Heuristic (Only used if Router enabled but failed)
        full_text = " ".join([self._extract_text_from_content(m.get("content")) for m in messages])
        
        if len(full_text) > 2000:
            return "t3"
        
        complex_keywords = [
            "code", "function", "complex", "analysis", "summary", "reasoning", "generate", "create",
            "代码", "函数", "分析", "总结", "推理", "生成", "创建", "搜索", "查询"
        ]
        if any(k in full_text.lower() for k in complex_keywords):
            return "t2"
            
        return "t1"

    async def route_request(self, request: ChatCompletionRequest, background_tasks: BackgroundTasks):
        trace_logger.log_separator("=")
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
            models = config.models.t1
            timeout_ms = config.timeouts.connect.get("t1", 5000)
            stream_timeout_ms = config.timeouts.generation.get("t1", 300000)
            max_rounds = config.retries.rounds.get("t1", 1)
        elif level == "t2":
            models = config.models.t2
            timeout_ms = config.timeouts.connect.get("t2", 15000)
            stream_timeout_ms = config.timeouts.generation.get("t2", 300000)
            max_rounds = config.retries.rounds.get("t2", 1)
        else: # t3
            models = config.models.t3
            timeout_ms = config.timeouts.connect.get("t3", 30000)
            stream_timeout_ms = config.timeouts.generation.get("t3", 300000)
            max_rounds = config.retries.rounds.get("t3", 1)
            
        if not models:
            raise HTTPException(status_code=500, detail=f"No models configured for level {level}")

        # Apply Routing Strategy
        strategy = config.routing_strategies.get(level, "sequential")
        sorted_models = self._get_sorted_models(models, strategy)
        
        # Apply Strategy-specific Retry Logic
        # Previous logic attempted to flatten retries into a single list for adaptive/random strategies.
        # However, this caused issues with retry counting and log continuity (User Feedback).
        # We now stick to the standard max_rounds loop for all strategies.
        # This means max_rounds controls how many times we cycle through the ENTIRE model list.
        # For adaptive/random, the order is determined once per request (above).
        
        # Log if strategy reordered them
        if strategy != "sequential" and sorted_models != models:
             logger.info(f"Models reordered by strategy '{strategy}' for level {level}: {sorted_models}")
        models = sorted_models

        last_error = None
        last_stack_trace = None
        user_prompt = self._extract_text_from_content(request.messages[-1].get("content")) if request.messages else ""
        
        # Ensure max_rounds is at least 1
        if max_rounds < 1: max_rounds = 1
        
        retry_count = 0
        attempt_errors = []
        excluded_models = set()
        
        for round_idx in range(max_rounds):
            round_failed_models = set()
            if round_idx > 0:
                logger.info(f"Starting Round {round_idx + 1}/{max_rounds} for level {level}")
                
            for model_id_entry in models:
                # Skip hard failures always, skip soft failures only for this round
                if model_id_entry in excluded_models or model_id_entry in round_failed_models:
                    continue
                
                # Check for active cooldown (Global Health Check)
                stats = self._get_model_stats(model_id_entry)
                if stats.get("cooldown_until", 0) > time.time():
                    logger.info(f"Skipping model {model_id_entry} due to active cooldown (Until {stats['cooldown_until']})")
                    # If all models are in cooldown, we might run out of models.
                    # But that's intended behavior: "Cool down" means don't use it.
                    continue

                try:
                    # Resolve Provider
                    target_model_id = model_id_entry
                    target_base_url = config.providers.upstream.base_url
                    target_api_key = config.providers.upstream.api_key
                    target_protocol = "openai"
                    # Default to upstream verify_ssl (fallback to True if missing in config object)
                    target_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)
                    provider_label = None
                    
                    # 1. Check if model entry has "provider/model" format
                    if "/" in model_id_entry:
                        parts = model_id_entry.split("/", 1)
                        provider_id = parts[0]
                        real_model_id = parts[1]
                        
                        if provider_id in config.providers.custom:
                            provider = config.providers.custom[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_model_id = real_model_id
                            target_protocol = getattr(provider, "protocol", "openai")
                            target_verify_ssl = getattr(provider, "verify_ssl", True)
                            provider_label = provider_id
                        else:
                            logger.warning(f"Provider '{provider_id}' not found for model '{model_id_entry}'. Using default upstream.")
                            pass 

                    # 2. Check model_provider_map if no prefix used (or prefix resolution failed/ignored)
                    elif model_id_entry in config.providers.map:
                        provider_id = config.providers.map[model_id_entry]
                        if provider_id in config.providers.custom:
                            provider = config.providers.custom[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_protocol = getattr(provider, "protocol", "openai")
                            target_verify_ssl = getattr(provider, "verify_ssl", True)
                            provider_label = provider_id
                        else:
                             logger.warning(f"Mapped provider '{provider_id}' not found for model '{model_id_entry}'. Using default upstream.")

                    # Construct Display Model Name (Provider/Model)
                    display_model_name = f"{provider_label}/{target_model_id}" if provider_label else target_model_id

                    # 2. Log: Model Call Start
                    call_start_time = time.time()
                    # Fix: Duration should be relative to previous step or just 0?
                    # The prompt says: "框架接收→首次调用"
                    # So duration_since_req is correct for "Framework Received -> First Call".
                    
                    duration_since_req = (call_start_time - start_time) * 1000
                    trace_logger.log(trace_id, "MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, details=f"正在尝试: {display_model_name}")
                    
                    add_trace_event("MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, model=display_model_name)
                    
                    logger.info(f"Trying model {display_model_name} (Provider URL: {target_base_url}) for level {level} (Round {round_idx + 1})")
                    
                    # Pass callback or wrapper to capture internal events if needed, or just return them
                    # Actually _call_upstream needs to return timing info or we pass a mutable object
                    # Let's pass trace_events list to _call_upstream? No, it's better to keep it clean.
                    # _call_upstream already logs to trace_logger. 
                    # We need to capture those times for DB too.
                    # Let's modify _call_upstream to return metadata along with response?
                    # Or pass the add_trace_event callback.
                    
                    response_data = await self._call_upstream(request, target_model_id, target_base_url, target_api_key, timeout_ms, stream_timeout_ms, trace_id, retry_count, call_start_time, add_trace_event, protocol=target_protocol, verify_ssl=target_verify_ssl)
                    
                    # Record Success for Adaptive Routing
                    self._record_success(model_id_entry)

                    # 3. Log: Full Response (Success)
                    end_time = time.time()
                    duration = (end_time - start_time) * 1000
                    
                    # Extract usage if available
                    token_source = "upstream"
                    # usage_info is NOT available here because it's local to _call_upstream
                    # We need _call_upstream to return usage info
                    if "usage" in response_data:
                         usage = response_data["usage"]
                         prompt_tokens = usage.get("prompt_tokens", 0)
                         completion_tokens = usage.get("completion_tokens", 0)
                    else:
                         # Fallback to local calculation (approximate since we don't have full context here easily without re-calculating)
                         # Actually, response_data SHOULD contain usage if _call_upstream constructed it correctly.
                         # If response_data has usage, we use it. 
                         # If not, we can try local calc but we need content.
                         token_source = "local"
                         # We don't have local_prompt_tokens here easily unless we recalc or pass it out.
                         # Let's trust _call_upstream to populate usage in response_data.
                         prompt_tokens = 0
                         completion_tokens = 0
                         
                         # Check if usage is inside response_data
                         if "usage" in response_data:
                             token_source = "upstream" # Oh wait, we just checked that above.
                             pass
                         else:
                             # Recalculate local tokens here if missing
                             # Get prompt messages
                             req_messages = request.messages
                             prompt_tokens = self._count_messages_tokens(req_messages, model_id_entry)
                             
                             # Get completion content
                             completion_content = ""
                             if "choices" in response_data and response_data["choices"]:
                                 completion_content = response_data["choices"][0]["message"].get("content", "")
                             completion_tokens = self._count_tokens(completion_content, model_id_entry)

                    # Log success (Async via BackgroundTasks)
                    background_tasks.add_task(
                        self._log_request,
                        level, display_model_name, duration, "success", user_prompt, request.model_dump_json(), json.dumps(response_data), trace_events, None, retry_count, prompt_tokens, completion_tokens, token_source
                    )
                    
                    trace_logger.log_separator("=")
                    return response_data
                except Exception as e:
                    # 4. Log: Retry/Fail
                    fail_time = time.time()
                    fail_duration = (fail_time - call_start_time) * 1000
                    
                    # Extract Reason from Exception
                    error_msg = str(e)
                    reason = "Unknown Error"
                    penalty = 1.0 # Default penalty
                    cooldown = 0 # Default cooldown (seconds)
                    
                    if "TTFT Timeout" in error_msg:
                        reason = "超首token限制时长"
                        penalty = 0.5 # Timeout is often transient
                    elif "Total Timeout" in error_msg:
                        reason = "超总限制时长"
                        penalty = 0.5
                    elif "Status Code Error" in error_msg:
                         # Extract code?
                         reason = "触发错误状态码"
                         if ":" in error_msg:
                             code_part = error_msg.split(':')[1].strip()
                             reason += f": {code_part}"
                             # Adjust penalty based on code
                             if "429" in code_part:
                                 penalty = 10.0 # Rate limit - Heavy penalty to avoid selection
                                 cooldown = 60 # Cooldown for 60s
                             elif "401" in code_part or "403" in code_part:
                                 penalty = 50.0 # Auth error - Very heavy penalty
                                 cooldown = 300 # Cooldown 5 mins
                             elif code_part.strip().startswith("5"):
                                 penalty = 1.0 # Server error
                    elif "Error Keyword Match" in error_msg:
                         reason = "错误关键词"
                         if ":" in error_msg:
                             reason += f": {error_msg.split(':')[1].strip()}"
                         penalty = 10.0
                         cooldown = 60 # Treat custom errors as serious
                    elif "Empty Response" in error_msg:
                        reason = "空返回"
                        penalty = 1.0
                    elif "Connect Timeout" in error_msg:
                        reason = "连接超时"
                        penalty = 0.5
                    elif "Upstream Error" in error_msg:
                         reason = "上游错误"
                         if ":" in error_msg:
                             # Keep more context for tooltip
                             reason += f": {error_msg.split(':', 1)[1].strip()}"
                         penalty = 1.0
                    else:
                        reason = error_msg # No truncation
                        penalty = 1.0

                    trace_logger.log(trace_id, "MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, details=f"原因: {reason} | 模型: {display_model_name}")
                    add_trace_event("MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, model=display_model_name, reason=reason)
                    
                    # Record Failure for Adaptive Routing with calculated penalty and cooldown
                    self._record_failure(model_id_entry, penalty=penalty, cooldown_seconds=cooldown)

                    # Accumulate error history
                    detailed_error = f"[Round {round_idx + 1}|{display_model_name}] {reason}"
                    if str(e) != reason:
                         detailed_error += f" ({str(e)})"
                    attempt_errors.append(detailed_error)

                    # Strategy: 
                    # 1. Hard Failures (Auth, Client Error) -> Exclude for entire request
                    if "401" in error_msg or "403" in error_msg or "404" in error_msg:
                         excluded_models.add(model_id_entry)
                    # 2. Rate Limit (429) -> Exclude for entire request to avoid spamming
                    #    If we had multiple API keys for the same model, we could retry, but here we assume 1:1 mapping.
                    elif "429" in error_msg:
                         excluded_models.add(model_id_entry)
                    # 3. Custom Retry Logic (Keywords/Status Codes) -> Exclude for this round only (Soft Failure)
                    #    If it matched a retry condition, we should retry it in next round (or other models).
                    elif "Error Keyword Match" in error_msg or "Status Code Error" in error_msg:
                         round_failed_models.add(model_id_entry)
                    # 4. Other Soft Failures (503 Service Unavailable, Timeout) -> Exclude for this round only
                    #    (This allows retrying in next round if max_rounds > 1)
                    elif "503" in error_msg or "Timeout" in error_msg:
                         round_failed_models.add(model_id_entry)

                    logger.error(f"Model {display_model_name} failed (Round {round_idx + 1}): {e}")
                    last_error = e
                    last_stack_trace = traceback.format_exc()
                    
                    # Increment retry count ONLY after full processing of failure
                    retry_count += 1
                    continue
                
        # All failed
        duration = (time.time() - start_time) * 1000
        trace_logger.log(trace_id, "ALL_FAILED", time.time(), duration, "fail", retry_count, details=f"所有 {len(models)} 个模型尝试均失败")
        add_trace_event("ALL_FAILED", time.time(), duration, "fail", retry_count)
        
        # Await logging directly to ensure it's recorded before raising exception
        await self._log_request(
            level, "all", duration, "error", user_prompt, request.model_dump_json(), str(last_error), trace_events, last_stack_trace, retry_count
        )
        
        trace_logger.log_separator("=")
        # Use 502 Bad Gateway to indicate upstream failure, but ensure it's a FINAL error
        # The user reported that "Retry 8" failure was followed by a NEW request.
        # This implies that the CLIENT (AstrBot or other) received an error code that triggered ITS OWN retry logic.
        # Standard HTTP error handling:
        # 500/502/503/504 -> Often triggers client retry.
        # 4xx -> Usually does not trigger client retry (unless 429).
        
        # If we have exhausted ALL retries internally, we should return a 502.
        # But if the client is aggressive, it might retry on 502.
        # We can't control the client, but we can ensure OUR logic stops here.
        # The logs show "全部尝试失败" then a NEW "收到请求". This confirms it's a NEW request from client.
        
        raise HTTPException(status_code=502, detail=f"All models failed after {retry_count} retries. Last error: {str(last_error)}")

    async def _call_upstream(self, request: ChatCompletionRequest, model_id: str, base_url: str, api_key: str, timeout_ms: int, stream_timeout_ms: int, trace_id: str, retry_count: int, req_start_time: float, trace_callback=None, protocol: str = "openai", verify_ssl: bool = True) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare payload
        payload = request.model_dump(exclude_none=True)
        payload["model"] = model_id
        
        # Check Protocol for Stream
        if protocol == "v1-messages":
            payload["stream"] = False
        else:
            payload["stream"] = True # Force stream for aggregation
        
        config = config_manager.get_config()
        
        # --- Parameter Merge Logic ---
        # Priority: Request > Model Specific > Global Default
        
        # 1. Global Defaults
        for key, value in config.params.global_params.items():
            if key not in payload:
                payload[key] = value
                
        # 2. Model Specific Defaults
        if model_id in config.params.model_params:
            for key, value in config.params.model_params[model_id].items():
                if key not in payload or request.model_dump().get(key) is None: 
                     pass

        # Re-construct payload to ensure correct precedence
        final_payload = {}
        
        # Base: Global Defaults
        final_payload.update(config.params.global_params)
        
        # Override: Model Specific Defaults
        if model_id in config.params.model_params:
            final_payload.update(config.params.model_params[model_id])
            
        # Override: Request Params (only if not None)
        request_dict = request.model_dump(exclude_none=True)
        final_payload.update(request_dict)
        
        # Ensure critical fields
        final_payload["model"] = model_id
        if protocol == "v1-messages":
            final_payload["stream"] = False
        else:
            final_payload["stream"] = True
            # Enable usage reporting for streaming
            final_payload["stream_options"] = {"include_usage": True}
        
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
        
        if self._client is None: await self.startup()

        # Handle v1-messages Protocol (No Stream, Different Endpoint Logic)
        if protocol == "v1-messages":
             # Perform Message Conversion (OpenAI -> Anthropic)
             conversion = self._convert_to_anthropic_messages(payload.get("messages", []))
             payload["messages"] = conversion["messages"]
             if conversion["system"]:
                 payload["system"] = conversion["system"]
             
             # Also convert tools if present
             if "tools" in payload:
                 anthropic_tools = []
                 for t in payload["tools"]:
                     if t.get("type") == "function":
                         func = t.get("function", {})
                         anthropic_tools.append({
                             "name": func.get("name"),
                             "description": func.get("description"),
                             "input_schema": func.get("parameters")
                         })
                 if anthropic_tools:
                     payload["tools"] = anthropic_tools
                     # Remove tool_choice if set to auto (default) or handle mapping
                     # OpenAI: tool_choice="auto" or {"type": "function", ...}
                     # Anthropic: tool_choice={"type": "auto"} or {"type": "tool", "name": "..."}
                     if "tool_choice" in payload:
                         tc = payload["tool_choice"]
                         if tc == "auto":
                             payload["tool_choice"] = {"type": "auto"}
                         elif isinstance(tc, dict) and tc.get("type") == "function":
                             payload["tool_choice"] = {"type": "tool", "name": tc.get("function", {}).get("name")}
                         elif tc == "none":
                             del payload["tool_choice"] # Anthropic doesn't use "none", just omit tools or choice
             
             base = base_url.rstrip('/')
             url = f"{base}/messages"
             
             try:
                 response = await self._client.post(url, json=payload, headers=headers, timeout=timeout_config, verify=verify_ssl)
                 
                 ttft_time = time.time()
                 duration_ttft = (ttft_time - req_start_time) * 1000
                 trace_logger.log(trace_id, "FIRST_TOKEN", ttft_time, duration_ttft, "success", retry_count, details=f"完整响应 (No Stream) | 模型: {model_id}")
                 if trace_callback:
                     trace_callback("FIRST_TOKEN", ttft_time, duration_ttft, "success", retry_count)

                 if response.status_code != 200:
                     error_str = response.text
                     should_retry = False
                     if response.status_code in config.retries.conditions.status_codes:
                         should_retry = True
                     
                     if not should_retry:
                         lower_error = error_str.lower()
                         for k in config.retries.conditions.error_keywords:
                             if k in lower_error:
                                 should_retry = True
                                 break
                     
                     if should_retry:
                         raise Exception(f"Upstream Error (Retryable): {response.status_code} - {error_str}")
                     else:
                         raise Exception(f"Upstream Error: {response.status_code} - {error_str}")

                 response_data = response.json()
                 
                 # 转换 v1/messages 响应格式为 OpenAI 兼容格式
                 if "choices" not in response_data and "content" in response_data:
                     # 提取 content 和 tool_calls
                     content_raw = response_data.get("content")
                     content_text = ""
                     tool_calls = []
                     
                     if isinstance(content_raw, str):
                         content_text = content_raw
                     elif isinstance(content_raw, list):
                         for item in content_raw:
                             if isinstance(item, dict):
                                 item_type = item.get("type")
                                 if item_type == "text":
                                     content_text += item.get("text", "")
                                 elif item_type == "tool_use":
                                     # 转换 Anthropic tool_use 到 OpenAI tool_call
                                     # Anthropic: {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
                                     # OpenAI: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
                                     tool_call = {
                                         "id": item.get("id"),
                                         "type": "function",
                                         "function": {
                                             "name": item.get("name"),
                                             # OpenAI expect arguments as a JSON string, Anthropic provides a dict
                                             "arguments": json.dumps(item.get("input", {}))
                                         }
                                     }
                                     tool_calls.append(tool_call)
                     
                     # 构造 Message 对象
                     message_obj = {
                         "role": response_data.get("role", "assistant"),
                         "content": content_text if content_text else None
                     }
                     if tool_calls:
                         message_obj["tool_calls"] = tool_calls
                     
                     # 构造 OpenAI 格式响应
                     mapped_response = {
                         "id": response_data.get("id", f"msg_{int(time.time())}"),
                         "object": "chat.completion",
                         "created": int(time.time()),
                         "model": response_data.get("model", model_id),
                         "choices": [
                             {
                                 "index": 0,
                                 "message": message_obj,
                                 "finish_reason": response_data.get("stop_reason", "stop")
                             }
                         ],
                         "usage": response_data.get("usage", {
                             "prompt_tokens": self._count_messages_tokens(request.messages, model_id),
                             "completion_tokens": self._count_tokens(content_text, model_id),
                             "total_tokens": 0
                         })
                     }
                     # 确保 usage 中的 key 是 OpenAI 兼容的 (Anthropic 使用 input_tokens/output_tokens)
                     if "input_tokens" in mapped_response["usage"]:
                         mapped_response["usage"]["prompt_tokens"] = mapped_response["usage"].pop("input_tokens")
                     if "output_tokens" in mapped_response["usage"]:
                         mapped_response["usage"]["completion_tokens"] = mapped_response["usage"].pop("output_tokens")
                     if "total_tokens" not in mapped_response["usage"]:
                         mapped_response["usage"]["total_tokens"] = mapped_response["usage"].get("prompt_tokens", 0) + mapped_response["usage"].get("completion_tokens", 0)
                         
                     response_data = mapped_response
                 
                 full_resp_time = time.time()
                 duration_since_ttft = (full_resp_time - ttft_time)*1000
                 
                 usage = response_data.get("usage", {})
                 p_tok = usage.get("prompt_tokens", 0)
                 c_tok = usage.get("completion_tokens", 0)
                 
                 trace_logger.log(trace_id, "FULL_RESPONSE", full_resp_time, duration_since_ttft, "success", retry_count, details=f"完整响应接收完毕 | Tokens: {p_tok}+{c_tok}")
                 if trace_callback:
                     trace_callback("FULL_RESPONSE", full_resp_time, duration_since_ttft, "success", retry_count)
                 
                 return response_data
                 
             except httpx.ReadTimeout:
                raise Exception("Total Timeout (Read): Read timeout from upstream")
             except httpx.ConnectTimeout:
                raise Exception("Connect Timeout: Connect timeout to upstream")
             except Exception:
                 raise

        try:
            # Manually manage the stream context to decouple TTFT timeout from Body timeout
            # Use global client with specific request timeout
            # Pass verify_ssl to handle self-signed certificates if configured
            ctx = self._client.stream("POST", f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=timeout_config, verify=verify_ssl)
            
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
            
            trace_logger.log(trace_id, "FIRST_TOKEN", ttft_time, duration_ttft, "success", retry_count, details=f"首字响应 | 模型: {model_id}")
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
                        if response.status_code in config.retries.conditions.status_codes:
                            should_retry = True
                        
                        # 2. Check Error Keyword Failover
                        keyword_match = None
                        if not should_retry:
                            lower_error = error_str.lower()
                            for k in config.retries.conditions.error_keywords:
                                if k in lower_error:
                                    should_retry = True
                                    keyword_match = k
                                    break
                        
                        if should_retry:
                            if keyword_match:
                                raise Exception(f"Error Keyword Match: {keyword_match} in {error_str}")
                            else:
                                raise Exception(f"Status Code Error: {response.status_code} - {error_str}")
                        else:
                            raise Exception(f"Upstream Error: {response.status_code} - {error_str}")

                    # Aggregate Stream
                    aggregated_content = ""
                    aggregated_tool_calls = {} # index -> tool_call
                    finish_reason = None
                    role = "assistant"
                    usage_info = None # Capture usage from stream options if available
                    prompt_tokens = 0
                    completion_tokens = 0
                    
                    # Pre-calculate prompt tokens locally just in case
                    # Use full messages list for accuracy, fallback to empty list
                    req_messages = payload.get("messages", [])
                    local_prompt_tokens = self._count_messages_tokens(req_messages, model_id)
                    
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
                                    # Always check for usage field first, regardless of choices
                                    if "usage" in chunk_json:
                                        usage_info = chunk_json["usage"]

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
                        if config.retries.conditions.retry_on_empty:
                            raise Exception("Empty Response: Upstream returned empty content and no tool calls")
                        else:
                            # If retry disabled, just return empty response (or handle gracefully)
                            pass # Continue to construct response

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
                    
                    # Calculate completion tokens locally if needed
                    local_completion_tokens = 0
                    if not usage_info:
                        local_completion_tokens = self._count_tokens(aggregated_content, model_id)

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
                        "usage": usage_info or {
                            "prompt_tokens": local_prompt_tokens,
                            "completion_tokens": local_completion_tokens,
                            "total_tokens": local_prompt_tokens + local_completion_tokens
                        }
                    }
                    
                    # 5. Log: Full Response
                    full_resp_time = time.time()
                    # Duration from First Token -> Full Return
                    duration_since_ttft = (full_resp_time - ttft_time)*1000
                    
                    final_usage = final_response["usage"]
                    p_tok = final_usage.get("prompt_tokens", 0)
                    c_tok = final_usage.get("completion_tokens", 0)
                    
                    trace_logger.log(trace_id, "FULL_RESPONSE", full_resp_time, duration_since_ttft, "success", retry_count, details=f"完整响应接收完毕 | Tokens: {p_tok}+{c_tok}")
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

    async def _log_request(self, level, model, duration, status, prompt, req_json, res_json, trace_data=None, stack_trace=None, retry_count=0, prompt_tokens=0, completion_tokens=0, token_source="upstream"):
        # This function is now run in background
        async with AsyncSessionLocal() as session:
            try:
                # Optimize Logging: Extract only necessary info
                
                # Determine Category
                category = "chat"
                try:
                    # Check for tool calls in response
                    if "tool_calls" in res_json:
                         category = "tool"
                    
                    # Check for tool calls in request (if any)
                    # Simple string check for speed
                    elif '"tool_calls":' in req_json or '"tools":' in req_json:
                         category = "tool"
                except:
                    pass

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
                    retry_count=retry_count,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    token_source=token_source
                )
                session.add(log_entry)
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to log request: {e}")

router_engine = RouterEngine()
