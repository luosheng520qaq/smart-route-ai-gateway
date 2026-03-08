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

from config_manager import config_manager, ModelEntry
from database import AsyncSessionLocal, RequestLog
from logger import trace_logger

# Configure logging
# Force simple print-based logger for immediate user feedback since logger config might be swallowing logs
class PrintLogger:
    def info(self, msg):
        print(f"[INFO] {msg}")
        trace_logger.buffer.append(msg)
        trace_logger.broadcast(msg)
    def warning(self, msg):
        print(f"[WARN] {msg}")
        trace_logger.buffer.append(msg)
        trace_logger.broadcast(msg)
    def error(self, msg):
        print(f"[ERROR] {msg}")
        trace_logger.buffer.append(msg)
        trace_logger.broadcast(msg)

logger = PrintLogger()

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
    response_format: Optional[Dict[str, Any]] = None

class RouterEngine:
    _client: Optional[httpx.AsyncClient] = None
    _model_stats: Dict[str, Dict[str, Any]] = {} # { "model_id": { "failures": 0.0, "success": 0, "last_updated": timestamp } }
    _stats_file: str = "model_stats.json"
    _tokenizer = None
    _image_description_cache: Dict[str, Dict[str, Any]] = {} # { "image_url_or_path": { "description": "...", "timestamp": 1234567890 } }
    _image_cache_file: str = "image_description_cache.json"
    
    def _normalize_model_entry(self, item: Any) -> Dict[str, Any]:
        """Normalize any model entry to a consistent dictionary format with 'model' and 'provider' fields."""
        if isinstance(item, dict):
            if "model" in item:
                # Already in new format
                result = item.copy()
                if "multimodal" not in result:
                    result["multimodal"] = True
                if "weight" not in result:
                    result["weight"] = 0.5
                return result
            else:
                # Old format dict without model field, treat as just model name
                # This shouldn't happen, but handle it just in case
                return {"model": str(item), "provider": "upstream", "multimodal": True, "weight": 0.5}
        elif isinstance(item, str):
            # Old format string
            if "/" in item:
                parts = item.split("/", 1)
                return {"model": parts[1], "provider": parts[0], "multimodal": True, "weight": 0.5}
            else:
                return {"model": item, "provider": "upstream", "multimodal": True, "weight": 0.5}
        elif hasattr(item, "model") and hasattr(item, "provider"):
            # Pydantic ModelEntry object
            result = {"model": item.model, "provider": item.provider}
            if hasattr(item, "multimodal"):
                result["multimodal"] = item.multimodal
            else:
                result["multimodal"] = True
            if hasattr(item, "weight"):
                result["weight"] = item.weight
            else:
                result["weight"] = 0.5
            return result
        else:
            # Fallback
            return {"model": str(item), "provider": "upstream", "multimodal": True, "weight": 0.5}
    
    def _extract_model_id(self, item: Any) -> str:
        """Extract a unique model ID for stats tracking (provider/model or just model)."""
        normalized = self._normalize_model_entry(item)
        if normalized["provider"] == "upstream":
            return normalized["model"]
        else:
            return f"{normalized['provider']}/{normalized['model']}"
    
    def _get_all_model_ids(self, config) -> List[str]:
        """Get all unique model IDs from config for stats initialization."""
        model_ids = []
        for level in ["t1", "t2", "t3"]:
            model_list = getattr(config.models, level, [])
            for item in model_list:
                model_ids.append(self._extract_model_id(item))
        return model_ids

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
        # Load image description cache from disk
        self._load_image_cache()
        
        # Pre-populate stats for all configured models (if not in file)
        config = config_manager.get_config()
        all_models = set(self._get_all_model_ids(config))
        for m in all_models:
            if m and m not in self._model_stats:
                self._model_stats[m] = {
                    "failures": 0, 
                    "success": 0, 
                    "failure_score": 0.0, 
                    "cooldown_until": 0,
                    "last_updated": time.time(),
                    "avg_response_time": 0.0,
                    "response_time_samples": []
                }

    async def shutdown(self):
        """Close global HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Global HTTP Client closed")
        # Save stats to disk
        self._save_stats()
        # Save image description cache to disk
        self._save_image_cache()

    def _load_image_cache(self):
        if os.path.exists(self._image_cache_file):
            try:
                with open(self._image_cache_file, 'r', encoding='utf-8') as f:
                    self._image_description_cache = json.load(f)
                logger.info("Image description cache loaded from disk")
            except Exception as e:
                logger.error(f"Failed to load image description cache: {e}")
                self._image_description_cache = {}

    def _save_image_cache(self):
        try:
            with open(self._image_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._image_description_cache, f, indent=2)
            logger.info("Image description cache saved to disk")
        except Exception as e:
            logger.error(f"Failed to save image description cache: {e}")

    def _cleanup_expired_image_cache(self):
        """清理过期的图片描述缓存"""
        config = config_manager.get_config()
        ttl = config.providers.image_description_cache_ttl or 86400
        now = time.time()
        
        expired_keys = []
        for key, value in self._image_description_cache.items():
            timestamp = value.get("timestamp", 0) if isinstance(value, dict) else 0
            if now - timestamp > ttl:
                expired_keys.append(key)
        
        if expired_keys:
            for key in expired_keys:
                del self._image_description_cache[key]
            logger.info(f"[图片描述] 清理了 {len(expired_keys)} 个过期缓存")
            self._save_image_cache()

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

    def _extract_image_urls(self, content: Any) -> List[str]:
        """Extract all image URLs or paths from message content."""
        image_urls = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in ["image_url", "image"]:
                        if "image_url" in item:
                            url = item["image_url"].get("url", "")
                            if url:
                                image_urls.append(url)
                        elif "url" in item:
                            url = item.get("url", "")
                            if url:
                                image_urls.append(url)
        return image_urls

    def _has_image_content(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if any message contains image content."""
        for msg in messages:
            content = msg.get("content")
            if self._extract_image_urls(content):
                return True
        return False

    async def _describe_image(self, image_url: str) -> str:
        """Describe an image using the configured image description models with automatic retry."""
        try:
            logger.info(f"[图片描述_DEBUG] _describe_image 开始执行, image_url: {image_url[:100] if image_url else 'None'}")
            self._cleanup_expired_image_cache()
            
            if image_url in self._image_description_cache:
                logger.info(f"[图片描述_DEBUG] 发现缓存")
                cache_entry = self._image_description_cache[image_url]
                if isinstance(cache_entry, dict) and "description" in cache_entry:
                    logger.info(f"[图片描述] 使用缓存: {image_url[:50]}...")
                    return cache_entry["description"]
                elif isinstance(cache_entry, str):
                    logger.info(f"[图片描述] 使用缓存(旧格式): {image_url[:50]}...")
                    return cache_entry

            config = config_manager.get_config()
            image_desc_models = config.providers.image_description
            logger.info(f"[图片描述_DEBUG] 配置的图片描述模型: {image_desc_models}")

            if not image_desc_models:
                logger.warning("[图片描述] 未配置图片描述模型")
                return f"[图片: {image_url}]"

            logger.info(f"[图片描述] 开始描述图片: {image_url[:50]}...")

            last_error = None
            for model_idx, model_item in enumerate(image_desc_models):
                logger.info(f"[图片描述_DEBUG] 处理第 {model_idx+1} 个模型: {model_item}")
                try:
                    normalized = self._normalize_model_entry(model_item)
                    model_name = normalized["model"]
                    provider_id = normalized["provider"]
                    logger.info(f"[图片描述_DEBUG] 归一化后 - model: {model_name}, provider: {provider_id}")

                    logger.info(f"[图片描述] 尝试使用: [{provider_id}] {model_name}")

                    target_base_url = config.providers.upstream.base_url
                    target_api_key = config.providers.upstream.api_key
                    target_protocol = getattr(config.providers.upstream, "protocol", "openai")
                    target_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)

                    logger.info(f"[图片描述_DEBUG] 上游配置 - base_url: {target_base_url}, verify_ssl: {target_verify_ssl}")

                    if provider_id != "upstream":
                        logger.info(f"[图片描述_DEBUG] 使用自定义提供商: {provider_id}")
                        if provider_id in config.providers.custom:
                            provider = config.providers.custom[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_protocol = getattr(provider, "protocol", "openai")
                            target_verify_ssl = getattr(provider, "verify_ssl", True)
                            logger.info(f"[图片描述_DEBUG] 自定义提供商配置 - base_url: {target_base_url}")
                        else:
                            logger.warning(f"[图片描述] Provider '{provider_id}' not found")
                            continue

                    headers = {
                        "Authorization": f"Bearer {target_api_key}",
                        "Content-Type": "application/json"
                    }

                    timeout_config = httpx.Timeout(
                        connect=10.0,
                        read=30.0,
                        write=10.0,
                        pool=10.0
                    )

                    prompt = config.providers.image_description_prompt or "请详细描述这张图片的内容，包括主要物体、场景、颜色、文字等信息。"
                    
                    payload = {
                        "model": model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": image_url}}
                                ]
                            }
                        ],
                        "max_tokens": 2048
                    }
                    logger.info(f"[图片描述_DEBUG] 请求载荷准备完成")

                    url = f"{target_base_url.rstrip('/')}/chat/completions"
                    logger.info(f"[图片描述_DEBUG] 请求URL: {url}")

                    temp_client = httpx.AsyncClient(verify=target_verify_ssl, timeout=timeout_config)
                    try:
                        logger.info(f"[图片描述_DEBUG] 发送HTTP请求...")
                        response = await temp_client.post(url, json=payload, headers=headers, timeout=timeout_config)
                        logger.info(f"[图片描述_DEBUG] 收到响应, status_code: {response.status_code}")
                        if response.status_code == 200:
                            resp_json = response.json()
                            logger.info(f"[图片描述_DEBUG] 响应JSON解析成功")
                            description = resp_json["choices"][0]["message"]["content"].strip()
                            self._image_description_cache[image_url] = {
                                "description": description,
                                "timestamp": time.time()
                            }
                            self._save_image_cache()
                            logger.info(f"[图片描述] 描述成功: {description[:100]}...")
                            return description
                        else:
                            logger.warning(f"[图片描述] 请求失败: {response.status_code} - {response.text[:200]}")
                            last_error = f"HTTP {response.status_code}"
                    finally:
                        await temp_client.aclose()

                except Exception as e:
                    logger.error(f"[图片描述] 异常: {str(e)}")
                    logger.error(f"[图片描述_DEBUG] 完整堆栈跟踪:\n{traceback.format_exc()}")
                    last_error = str(e)
                    continue

            logger.error(f"[图片描述] 所有模型都失败了: {last_error}")
            return f"[图片: {image_url}]"
        except Exception as e:
            logger.error(f"[图片描述] 致命错误: {str(e)}")
            logger.error(f"[图片描述_DEBUG] 致命错误完整堆栈跟踪:\n{traceback.format_exc()}")
            return f"[图片: {image_url}]"

    async def _process_messages_with_images(self, messages: List[Dict[str, Any]], preserve_original: bool = True) -> List[Dict[str, Any]]:
        """
        Process messages: if they contain images, describe them and create a cleaned version.
        If preserve_original is True, keeps the original images in a structured way for tool calls.
        """
        logger.info(f"[图片处理_DEBUG] _process_messages_with_images 开始执行, 消息数量: {len(messages)}, preserve_original: {preserve_original}")
        processed_messages = []
        
        for msg_idx, msg in enumerate(messages):
            logger.info(f"[图片处理_DEBUG] 处理第 {msg_idx+1} 条消息")
            content = msg.get("content")
            logger.info(f"[图片处理_DEBUG] 消息内容类型: {type(content)}")
            image_urls = self._extract_image_urls(content)
            logger.info(f"[图片处理_DEBUG] 提取到 {len(image_urls)} 张图片")
            
            if not image_urls:
                logger.info(f"[图片处理_DEBUG] 无图片，直接复制消息")
                processed_messages.append(msg.copy())
                continue

            if preserve_original:
                logger.info(f"[图片处理_DEBUG] preserve_original=True，仅缓存图片描述，不修改请求体")
                if isinstance(content, list):
                    image_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") in ["image_url", "image"]:
                            image_parts.append(item)
                    
                    for img_item in image_parts:
                        img_url = None
                        if "image_url" in img_item:
                            img_url = img_item["image_url"].get("url", "")
                        elif "url" in img_item:
                            img_url = img_item.get("url", "")
                        
                        if img_url:
                            try:
                                logger.info(f"[图片处理_DEBUG] 调用 _describe_image 缓存描述: {img_url[:100]}")
                                await self._describe_image(img_url)
                                logger.info(f"[图片处理_DEBUG] 图片描述缓存成功")
                            except Exception as e:
                                logger.error(f"[图片处理] 缓存图片描述失败: {str(e)}")
                                logger.error(f"[图片处理_DEBUG] 缓存图片描述完整堆栈跟踪:\n{traceback.format_exc()}")
                
                processed_messages.append(msg.copy())
                logger.info(f"[图片处理_DEBUG] preserve_original=True，返回原始消息")
                continue

            new_msg = msg.copy()
            
            if isinstance(content, list):
                logger.info(f"[图片处理_DEBUG] content是list类型，开始处理")
                text_parts = []
                image_parts = []
                
                for item_idx, item in enumerate(content):
                    logger.info(f"[图片处理_DEBUG] 处理第 {item_idx+1} 个content项: {type(item)}")
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                            logger.info(f"[图片处理_DEBUG] 文本项已添加")
                        elif item.get("type") in ["image_url", "image"]:
                            image_parts.append(item)
                            logger.info(f"[图片处理_DEBUG] 图片项已添加")
                
                logger.info(f"[图片处理_DEBUG] 文本部分: {text_parts}, 图片部分数量: {len(image_parts)}")
                
                descriptions = []
                for img_idx, img_item in enumerate(image_parts):
                    logger.info(f"[图片处理_DEBUG] 描述第 {img_idx+1} 张图片")
                    img_url = None
                    if "image_url" in img_item:
                        img_url = img_item["image_url"].get("url", "")
                    elif "url" in img_item:
                        img_url = img_item.get("url", "")
                    
                    if img_url:
                        try:
                            logger.info(f"[图片处理_DEBUG] 调用 _describe_image 处理URL: {img_url[:100]}")
                            desc = await self._describe_image(img_url)
                            descriptions.append((img_url, desc))
                            logger.info(f"[图片处理_DEBUG] 图片描述成功")
                        except Exception as e:
                            logger.error(f"[图片处理] 描述图片失败: {str(e)}")
                            logger.error(f"[图片处理_DEBUG] 描述图片完整堆栈跟踪:\n{traceback.format_exc()}")
                            descriptions.append((img_url, f"[图片: {img_url}]"))
                
                new_text = "\n".join(text_parts)
                for img_url, desc in descriptions:
                    new_text += f"\n\n[图片描述: {desc}]"
                logger.info(f"[图片处理_DEBUG] 新文本内容: {new_text[:200]}...")
                
                new_msg["content"] = new_text
                logger.info(f"[图片处理_DEBUG] preserve_original=False，保留图片URL和描述")
            elif isinstance(content, str):
                new_msg["content"] = content
                logger.info(f"[图片处理_DEBUG] content是str类型")
            else:
                new_msg["content"] = content
                logger.info(f"[图片处理_DEBUG] content是其他类型: {type(content)}")
            
            processed_messages.append(new_msg)
            logger.info(f"[图片处理_DEBUG] 第 {msg_idx+1} 条消息处理完成")
        
        logger.info(f"[图片处理_DEBUG] _process_messages_with_images 执行完成，返回 {len(processed_messages)} 条消息")
        return processed_messages

    def _get_model_stats(self, model_id: str) -> Dict[str, Any]:
        if model_id not in self._model_stats:
            self._model_stats[model_id] = {
                "failures": 0, 
                "success": 0, 
                "failure_score": 0.0, 
                "cooldown_until": 0,
                "last_updated": time.time(),
                "avg_response_time": 0.0,
                "response_time_samples": []
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
        
        if "avg_response_time" not in stats:
            stats["avg_response_time"] = 0.0
        if "response_time_samples" not in stats:
            stats["response_time_samples"] = []
            
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

    def _record_response_time(self, model_id: str, response_time_ms: float):
        stats = self._get_model_stats(model_id)
        samples = stats.get("response_time_samples", [])
        
        samples.append(response_time_ms)
        
        max_samples = 20
        if len(samples) > max_samples:
            samples = samples[-max_samples:]
        
        stats["response_time_samples"] = samples
        stats["avg_response_time"] = sum(samples) / len(samples)
        
        self._save_stats()

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
        current_models = set(self._get_all_model_ids(config))
        
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

    def _get_sorted_models(self, models: List[Any], strategy: str) -> List[Any]:
        if not models:
            return []
        
        logger.info("=" * 60)
        logger.info(f"[模型排序] 策略: {strategy.upper()}")
        logger.info("=" * 60)
        
        # 打印原始模型列表（带提供商信息）
        logger.info("📋 原始模型列表:")
        for idx, m in enumerate(models):
            normalized = self._normalize_model_entry(m)
            provider_tag = f"[{normalized['provider']}]"
            weight = normalized.get("weight", 0.5)
            logger.info(f"  {idx + 1}. {provider_tag} {normalized['model']} | 用户权重: {weight:.2f}")
        
        logger.info("-" * 60)
            
        if strategy == "sequential":
            logger.info("✅ 使用顺序策略，保持原始顺序")
            logger.info("=" * 60)
            return models
            
        if strategy == "random":
            # Pure random shuffle
            shuffled = list(models)
            random.shuffle(shuffled)
            logger.info("🎲 使用随机策略，已打乱顺序:")
            for idx, m in enumerate(shuffled):
                normalized = self._normalize_model_entry(m)
                provider_tag = f"[{normalized['provider']}]"
                logger.info(f"  {idx + 1}. {provider_tag} {normalized['model']}")
            logger.info("=" * 60)
            return shuffled
            
        if strategy == "adaptive":
            config = config_manager.get_config()
            weights = config.adaptive_weights
            
            logger.info("🧠 使用自适应策略，计算各模型权重（随机数 + 健康度 + 响应时间 + 用户权重）...")
            logger.info(f"📊 权重占比: 随机数 {weights.weight_random} | 健康值 {weights.weight_health} | 响应速度 {weights.weight_speed} | 用户加权 {weights.weight_user}")
            
            scored_models = []
            max_response_time_threshold = 30000.0
            
            # 权重配置
            WEIGHT_RANDOM = weights.weight_random
            WEIGHT_HEALTH = weights.weight_health
            WEIGHT_SPEED = weights.weight_speed
            WEIGHT_USER = weights.weight_user
            
            for m in models:
                model_id = self._extract_model_id(m)
                self._refresh_stats(model_id)
                stats = self._get_model_stats(model_id)
                
                normalized = self._normalize_model_entry(m)
                provider_tag = f"[{normalized['provider']}]"
                health_score = stats.get("health_score", 100)
                cooldown_active = stats.get("cooldown_until", 0) > time.time()
                
                # 1. 随机因子 - 归一化到 [0, 1]
                random_factor = random.random()
                
                # 2. 健康因子 - 归一化到 [0, 1]
                health_factor = health_score / 100.0
                
                # 3. 响应速度因子 - 归一化到 [0, 1]
                avg_response_time = stats.get("avg_response_time", 0.0)
                if avg_response_time > 0:
                    # 简单但有效的线性转换
                    # 0ms → 1.0, 30000ms → 0.0
                    normalized_time = min(avg_response_time / max_response_time_threshold, 1.0)
                    speed_factor = 1.0 - normalized_time
                else:
                    # 无历史数据：给予较高默认值（0.8），鼓励尝试新模型
                    speed_factor = 0.8
                
                # 4. 用户权重 - 归一化到 [0, 1]
                user_weight = normalized.get("weight", 0.5)
                user_weight = max(0.0, min(1.0, user_weight))
                
                # 加权求和
                score = (
                    random_factor * WEIGHT_RANDOM +
                    health_factor * WEIGHT_HEALTH +
                    speed_factor * WEIGHT_SPEED +
                    user_weight * WEIGHT_USER
                )
                
                status_icon = "🔴" if cooldown_active else "🟢"
                logger.info(
                    f"  {status_icon} {provider_tag} {normalized['model']} | "
                    f"健康度: {health_score}% | 响应时间: {avg_response_time:.0f}ms | "
                    f"随机: {random_factor:.3f} | 健康: {health_factor:.3f} | "
                    f"速度: {speed_factor:.3f} | 用户权重: {user_weight:.3f} | "
                    f"最终得分: {score:.4f}"
                )
                scored_models.append((score, m))
            
            scored_models.sort(key=lambda x: x[0], reverse=True)
            sorted_result = [m for _, m in scored_models]
            
            logger.info("-" * 60)
            logger.info("✅ 自适应排序完成，最终尝试顺序:")
            for idx, m in enumerate(sorted_result):
                normalized = self._normalize_model_entry(m)
                provider_tag = f"[{normalized['provider']}]"
                prefix = "➜" if idx == 0 else "  "
                logger.info(f"  {prefix} {idx + 1}. {provider_tag} {normalized['model']}")
            
            logger.info("=" * 60)
            return sorted_result
            
        logger.info("=" * 60)
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

    def _convert_content_to_v1_response(self, content: Any, mode: str = "input") -> List[Dict[str, Any]]:
        """
        Convert OpenAI content format to v1/responses format.
        mode: "input" for user messages, "output" for assistant messages
        """
        if content is None:
            return []
        if isinstance(content, str):
            text_type = "input_text" if mode == "input" else "output_text"
            return [{"type": text_type, "text": content}]
        if isinstance(content, list):
            result = []
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        text_type = "input_text" if mode == "input" else "output_text"
                        result.append({"type": text_type, "text": item.get("text", "")})
                    elif item_type == "image_url":
                        result.append({
                            "type": "input_image",
                            "image_url": item.get("image_url", {}).get("url", "")
                        })
            return result
        text_type = "input_text" if mode == "input" else "output_text"
        return [{"type": text_type, "text": str(content)}]

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
                # FORCE DISABLE SSL VERIFICATION as requested by user -> NOW CONFIGURABLE
                # verify_ssl = False (OLD)
                
                # Logic to inherit from Upstream if Router config is empty
                base_url = config.router.base_url
                api_key = config.router.api_key
                should_verify_ssl = config.router.verify_ssl # Default True in config

                if not base_url:
                    logger.info("Router Base URL is empty. Inheriting from Upstream Provider.")
                    base_url = config.providers.upstream.base_url
                    # Inherit SSL setting if inheriting URL
                    # Note: config.providers.upstream.verify_ssl might be None/False/True. 
                    # Pydantic defaults verify_ssl=True if not set in UpstreamConfig, 
                    # but let's check explicit attribute to be safe.
                    should_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)
                
                if not api_key:
                    logger.info("Router API Key is empty. Inheriting from Upstream Provider.")
                    api_key = config.providers.upstream.api_key

                # Handle SSL verification logic manually since httpx.post doesn't support 'verify' arg
                # Wait, httpx.AsyncClient supports verify. httpx.post is a shortcut.
                # We are using client_to_use.post where client_to_use is an instance.
                
                temp_client = httpx.AsyncClient(verify=should_verify_ssl, timeout=30.0)
                client_to_use = temp_client
                
                try:
                    base_url = base_url.rstrip('/')
                    # Prevent double path appending - Improved Logic
                    if base_url.endswith("/chat/completions"):
                         url = base_url
                    elif base_url.endswith("/"):
                         url = f"{base_url}chat/completions"
                    else:
                         url = f"{base_url}/chat/completions"
                        
                    logger.info(f"Router requesting URL: {url} (SSL Verify: {should_verify_ssl})")
                    
                    # Print full debug info for user
                    masked_key = api_key[:8] + "***" if api_key else "None"
                    logger.info(f"DEBUG: Router Request -> Model: {config.router.model}, URL: {url}, Auth: {masked_key}")
                    
                    resp = await client_to_use.post(
                        url,
                        json={
                            "model": config.router.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 10,
                            "temperature": 0.0
                        },
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=30.0
                    )
                    
                    if resp.status_code != 200:
                        logger.error(f"DEBUG: Router 404/Error Response Body: {resp.text}")
                finally:
                    if temp_client:
                        await temp_client.aclose()
                    
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
                    
                    # If parsing fails
                    raise Exception(f"Router response parsing failed. Content: {content[:100]}")
                else:
                    # Handle non-200 status codes
                    raise Exception(f"Router API returned status {resp.status_code}: {resp.text[:200]}")

            except Exception as e:
                logger.error(f"Router Model failed: {e}")
                if trace_callback:
                     trace_callback("ROUTER_FAIL", time.time(), 0, "fail", 0)
                # Directly raise exception as requested by user, NO HEURISTIC FALLBACK
                raise HTTPException(status_code=500, detail=f"Router Model Failed: {str(e)}")
        else:
            # If Router disabled, as requested by user, we default to T1 only.
            # This allows T1 to act as a fault-tolerant/fallback pool.
            logger.info("Router disabled. Defaulting to T1 level for fault tolerance.")
            return "t1"

    async def route_request(self, request: ChatCompletionRequest, background_tasks: BackgroundTasks):
        trace_logger.log_separator("=")
        start_time = time.time() # Request Arrived (T0)
        trace_id = str(uuid.uuid4())
        
        # 🎯 请求开始 - 美观的标题日志
        logger.info("")
        logger.info("╔" + "═" * 58 + "╗")
        logger.info("║" + " " * 15 + "🚀 新请求到达" + " " * 33 + "║")
        logger.info("╚" + "═" * 58 + "╝")
        logger.info(f"📌 Trace ID: {trace_id[:8]}...")
        
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
        
        logger.info("")
        logger.info("📊 正在确定请求级别...")
        level = await self.determine_level(request.messages, trace_callback=add_trace_event)
        logger.info(f"✅ 请求级别确定: {level.upper()}")
        
        models = []
        timeout_ms = 0
        stream_timeout_ms = 0
        
        # 根据策略类型选择不同的重试配置
        strategy = config.routing_strategies.get(level, "sequential")
        
        if level == "t1":
            models = config.models.t1
            timeout_ms = config.timeouts.connect.get("t1", 5000)
            stream_timeout_ms = config.timeouts.generation.get("t1", 300000)
            if strategy == "sequential":
                max_attempts = config.retries.rounds.get("t1", 1)
            else:
                max_attempts = config.retries.max_retries.get("t1", 3)
        elif level == "t2":
            models = config.models.t2
            timeout_ms = config.timeouts.connect.get("t2", 15000)
            stream_timeout_ms = config.timeouts.generation.get("t2", 300000)
            if strategy == "sequential":
                max_attempts = config.retries.rounds.get("t2", 1)
            else:
                max_attempts = config.retries.max_retries.get("t2", 3)
        else: # t3
            models = config.models.t3
            timeout_ms = config.timeouts.connect.get("t3", 30000)
            stream_timeout_ms = config.timeouts.generation.get("t3", 300000)
            if strategy == "sequential":
                max_attempts = config.retries.rounds.get("t3", 1)
            else:
                max_attempts = config.retries.max_retries.get("t3", 3)
            
        if not models:
            raise HTTPException(status_code=500, detail=f"No models configured for level {level}")

        # Apply Routing Strategy
        sorted_models = self._get_sorted_models(models, strategy)
        
        # 策略说明:
        # - 顺序模式 (sequential): max_attempts 表示轮询整个模型列表的次数
        # - 自适应/随机模式 (adaptive/random): max_attempts 表示最多尝试多少个不同的模型
        
        # Log if strategy reordered them
        if strategy != "sequential" and sorted_models != models:
             logger.info(f"Models reordered by strategy '{strategy}' for level {level}: {sorted_models}")
        models = sorted_models

        last_error = None
        last_stack_trace = None
        user_prompt = self._extract_text_from_content(request.messages[-1].get("content")) if request.messages else ""
        
        # Ensure max_attempts is at least 1
        if max_attempts < 1: max_attempts = 1
        
        retry_count = 0
        attempt_errors = []
        excluded_models = set()
        
        # 对于顺序模式，需要嵌套循环（轮数 × 模型数）
        # 对于自适应/随机模式，只需要单层循环（最多尝试 max_attempts 个模型）
        if strategy == "sequential":
            # 顺序模式：轮询整个列表 max_attempts 次
            total_models_to_try = len(models) * max_attempts
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"[模型选择] 顺序模式 | 轮询次数: {max_attempts} | 模型数: {len(models)} | 总尝试上限: {total_models_to_try}")
            logger.info("=" * 60)
            
            attempt_idx = 0
            for round_idx in range(max_attempts):
                round_failed_models = set()
                if round_idx > 0:
                    logger.info(f"Starting Round {round_idx + 1}/{max_attempts} for level {level}")
                    
                for model_idx, model_item in enumerate(models):
                    attempt_idx += 1
                    normalized = self._normalize_model_entry(model_item)
                    model_name = normalized["model"]
                    provider_id = normalized["provider"]
                    model_id_for_stats = self._extract_model_id(model_item)
                    
                    provider_tag = f"[{provider_id}]"
                    
                    logger.info(f"  ┌──────────────────────────────────────────────")
                    logger.info(f"  │ 🧪 尝试 {attempt_idx}/{total_models_to_try}: {provider_tag} {model_name} (轮次 {round_idx + 1})")
                    logger.info(f"  │    统计ID: {model_id_for_stats}")
                    
                    # Skip hard failures always, skip soft failures only for this round
                    if model_id_for_stats in excluded_models or model_id_for_stats in round_failed_models:
                        reason = "排除列表" if model_id_for_stats in excluded_models else "本回合失败"
                        logger.info(f"  │ ❌ 跳过: {reason}")
                        logger.info(f"  └──────────────────────────────────────────────")
                        continue
                    
                    # Check for active cooldown (Global Health Check)
                    stats = self._get_model_stats(model_id_for_stats)
                    if stats.get("cooldown_until", 0) > time.time():
                        cooldown_remaining = int(stats["cooldown_until"] - time.time())
                        logger.info(f"  │ ❌ 跳过: 冷却中 (剩余 {cooldown_remaining} 秒)")
                        logger.info(f"  └──────────────────────────────────────────────")
                        continue
                    
                    logger.info(f"  │ ✅ 通过检查，准备尝试...")
                    logger.info(f"  └──────────────────────────────────────────────")
                    
                    # === 尝试模型的代码 ===
                    try:
                        # Resolve Provider
                        target_model_id = model_name
                        target_base_url = config.providers.upstream.base_url
                        target_api_key = config.providers.upstream.api_key
                        target_protocol = getattr(config.providers.upstream, "protocol", "openai")
                        target_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)
                        provider_label = None
                        
                        if provider_id != "upstream":
                            if provider_id in config.providers.custom:
                                provider = config.providers.custom[provider_id]
                                target_base_url = provider.base_url
                                target_api_key = provider.api_key
                                target_protocol = getattr(provider, "protocol", "openai")
                                target_verify_ssl = getattr(provider, "verify_ssl", True)
                                provider_label = provider_id
                            else:
                                logger.warning(f"Provider '{provider_id}' not found for model '{model_name}'. Using default upstream.")
                                pass 

                        elif model_name in config.providers.map:
                            mapped_provider_id = config.providers.map[model_name]
                            if mapped_provider_id in config.providers.custom:
                                provider = config.providers.custom[mapped_provider_id]
                                target_base_url = provider.base_url
                                target_api_key = provider.api_key
                                target_protocol = getattr(provider, "protocol", "openai")
                                target_verify_ssl = getattr(provider, "verify_ssl", True)
                                provider_label = mapped_provider_id
                            else:
                                 logger.warning(f"Mapped provider '{provider_id}' not found for model '{model_name}'. Using default upstream.")

                        if provider_label:
                            display_model_name = f"{provider_label}/{target_model_id}"
                        else:
                            display_model_name = f"upstream/{target_model_id}"

                        call_start_time = time.time()
                        duration_since_req = (call_start_time - start_time) * 1000
                        trace_logger.log(trace_id, "MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, details=f"正在尝试: {display_model_name}")
                        add_trace_event("MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, model=display_model_name)
                        
                        logger.info("")
                        logger.info("  " + "─" * 56)
                        logger.info(f"  📤 正在请求: {display_model_name}")
                        logger.info(f"     提供商URL: {target_base_url}")
                        logger.info("  " + "─" * 56)
                        
                        logger.info(f"  [图片处理_DEBUG] 开始检查图片内容...")
                        has_images = self._has_image_content(request.messages)
                        model_multimodal = normalized.get("multimodal", True)
                        logger.info(f"  [图片处理_DEBUG] has_images: {has_images}, model_multimodal: {model_multimodal}")
                        
                        processed_request = request
                        log_messages = request.messages
                        if has_images:
                            try:
                                if not model_multimodal:
                                    logger.info(f"  [图片处理] 检测到图片内容，但模型不支持多模态。开始图片转述...")
                                    image_start_time = time.time()
                                    add_trace_event("IMAGE_TRANSCRIBE_START", image_start_time, 0, "success", retry_count)
                                    
                                    logger.info(f"  [图片处理_DEBUG] 调用 _process_messages_with_images, preserve_original=False")
                                    processed_messages = await self._process_messages_with_images(
                                        request.messages, 
                                        preserve_original=False
                                    )
                                    logger.info(f"  [图片处理_DEBUG] _process_messages_with_images 完成，构建新请求")
                                    processed_request = ChatCompletionRequest(
                                        model=request.model,
                                        messages=processed_messages,
                                        temperature=request.temperature,
                                        top_p=request.top_p,
                                        n=request.n,
                                        stream=request.stream,
                                        stop=request.stop,
                                        max_tokens=request.max_tokens,
                                        presence_penalty=request.presence_penalty,
                                        frequency_penalty=request.frequency_penalty,
                                        logit_bias=request.logit_bias,
                                        user=request.user,
                                        tools=request.tools,
                                        tool_choice=request.tool_choice,
                                        response_format=request.response_format
                                    )
                                    log_messages = processed_messages
                                    
                                    image_end_time = time.time()
                                    image_duration = (image_end_time - image_start_time) * 1000
                                    add_trace_event("IMAGE_TRANSCRIBE_DONE", image_end_time, image_duration, "success", retry_count)
                                    logger.info(f"  [图片处理] 图片转述完成，准备发送请求")
                                else:
                                    logger.info(f"  [图片处理] 检测到图片内容，模型支持多模态。先描述图片以缓存，然后保留原始图片...")
                                    image_start_time = time.time()
                                    add_trace_event("IMAGE_CACHE_START", image_start_time, 0, "success", retry_count)
                                    
                                    logger.info(f"  [图片处理_DEBUG] 调用 _process_messages_with_images, preserve_original=True")
                                    processed_messages = await self._process_messages_with_images(
                                        request.messages, 
                                        preserve_original=True
                                    )
                                    logger.info(f"  [图片处理_DEBUG] _process_messages_with_images 完成，构建新请求")
                                    processed_request = ChatCompletionRequest(
                                        model=request.model,
                                        messages=processed_messages,
                                        temperature=request.temperature,
                                        top_p=request.top_p,
                                        n=request.n,
                                        stream=request.stream,
                                        stop=request.stop,
                                        max_tokens=request.max_tokens,
                                        presence_penalty=request.presence_penalty,
                                        frequency_penalty=request.frequency_penalty,
                                        logit_bias=request.logit_bias,
                                        user=request.user,
                                        tools=request.tools,
                                        tool_choice=request.tool_choice,
                                        response_format=request.response_format
                                    )
                                    log_messages = processed_messages
                                    
                                    image_end_time = time.time()
                                    image_duration = (image_end_time - image_start_time) * 1000
                                    add_trace_event("IMAGE_CACHE_DONE", image_end_time, image_duration, "success", retry_count)
                                    logger.info(f"  [图片处理] 图片描述缓存完成，保留原始图片")
                            except Exception as e:
                                logger.error(f"  [图片处理] 图片处理流程异常: {str(e)}")
                                logger.error(f"  [图片处理_DEBUG] 图片处理流程完整堆栈跟踪:\n{traceback.format_exc()}")
                                logger.warning(f"  [图片处理] 图片处理失败，将使用原始请求继续尝试")
                        
                        response_data = await self._call_upstream(processed_request, target_model_id, target_base_url, target_api_key, timeout_ms, stream_timeout_ms, trace_id, retry_count, call_start_time, add_trace_event, protocol=target_protocol, verify_ssl=target_verify_ssl)
                        
                        self._record_success(model_id_for_stats)

                        end_time = time.time()
                        duration = (end_time - start_time) * 1000
                        
                        self._record_response_time(model_id_for_stats, duration)
                        
                        token_source = "upstream"
                        if "usage" in response_data:
                             usage = response_data["usage"]
                             prompt_tokens = usage.get("prompt_tokens", 0)
                             completion_tokens = usage.get("completion_tokens", 0)
                        else:
                             token_source = "local"
                             prompt_tokens = 0
                             completion_tokens = 0
                             if "usage" not in response_data:
                                 req_messages = request.messages
                                 prompt_tokens = self._count_messages_tokens(req_messages, model_name)
                                 completion_content = ""
                                 if "choices" in response_data and response_data["choices"]:
                                     completion_content = response_data["choices"][0]["message"].get("content", "")
                                 completion_tokens = self._count_tokens(completion_content, model_name)

                        logger.info("")
                        logger.info("  " + "─" * 56)
                        logger.info(f"  ✅ 请求成功!")
                        logger.info(f"  🤖 使用模型: {display_model_name}")
                        logger.info(f"  ⏱️  总耗时: {duration:.1f}ms")
                        logger.info(f"  📊 Token使用: {prompt_tokens} + {completion_tokens} = {prompt_tokens + completion_tokens}")
                        logger.info("  " + "─" * 56)
                        logger.info("")
                        logger.info("╔" + "═" * 58 + "╗")
                        logger.info("║" + " " * 18 + "🏁 请求完成" + " " * 30 + "║")
                        logger.info("╚" + "═" * 58 + "╝")
                        logger.info("")

                        background_tasks.add_task(
                            self._log_request,
                            level, display_model_name, duration, "success", 
                            self._extract_text_from_content(log_messages[-1].get("content")) if log_messages else user_prompt, 
                            json.dumps({**request.model_dump(), "messages": log_messages}), 
                            json.dumps(response_data), 
                            trace_events, None, retry_count, prompt_tokens, completion_tokens, token_source
                        )
                        
                        trace_logger.log_separator("=")
                        return response_data
                    except Exception as e:
                        fail_time = time.time()
                        fail_duration = (fail_time - call_start_time) * 1000
                        
                        error_msg = str(e)
                        reason = "Unknown Error"
                        penalty = 1.0
                        cooldown = 0
                        
                        if "TTFT Timeout" in error_msg:
                            reason = "超首token限制时长"
                            penalty = 0.5
                        elif "Total Timeout" in error_msg:
                            reason = "超总限制时长"
                            penalty = 0.5
                        elif "Status Code Error" in error_msg:
                             reason = "触发错误状态码"
                             if ":" in error_msg:
                                 code_part = error_msg.split(':')[1].strip()
                                 reason += f": {code_part}"
                                 if "429" in code_part:
                                     penalty = 10.0
                                     cooldown = 60
                                 elif "401" in code_part or "403" in code_part:
                                     penalty = 50.0
                                     cooldown = 300
                                 elif code_part.strip().startswith("5"):
                                     penalty = 1.0
                        elif "Error Keyword Match" in error_msg:
                             reason = "错误关键词"
                             if ":" in error_msg:
                                 reason += f": {error_msg.split(':')[1].strip()}"
                             penalty = 10.0
                             cooldown = 60
                        elif "Empty Response" in error_msg:
                            reason = "空返回"
                            penalty = 1.0
                        elif "Connect Timeout" in error_msg:
                            reason = "连接超时"
                            penalty = 0.5
                        elif "Upstream Error" in error_msg:
                             reason = "上游错误"
                             if ":" in error_msg:
                                 reason += f": {error_msg.split(':', 1)[1].strip()}"
                             penalty = 1.0
                        else:
                            reason = error_msg
                            penalty = 1.0

                        logger.info("")
                        logger.info("  " + "─" * 56)
                        logger.info(f"  ❌ 模型请求失败")
                        logger.info(f"  🤖 模型: {display_model_name}")
                        logger.info(f"  ⚠️  原因: {reason}")
                        logger.info(f"  ⏱️  耗时: {fail_duration:.1f}ms")
                        if cooldown > 0:
                            logger.info(f"  🕒  冷却: {cooldown}秒")
                        logger.info("  " + "─" * 56)
                        
                        trace_logger.log(trace_id, "MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, details=f"原因: {reason} | 模型: {display_model_name}")
                        add_trace_event("MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, model=display_model_name, reason=reason)
                        
                        self._record_failure(model_id_for_stats, penalty=penalty, cooldown_seconds=cooldown)

                        detailed_error = f"[Round {round_idx + 1}|{display_model_name}] {reason}"
                        if str(e) != reason:
                             detailed_error += f" ({str(e)})"
                        attempt_errors.append(detailed_error)

                        if "401" in error_msg or "403" in error_msg or "404" in error_msg:
                             excluded_models.add(model_id_for_stats)
                        elif "429" in error_msg:
                             excluded_models.add(model_id_for_stats)
                        elif "Error Keyword Match" in error_msg or "Status Code Error" in error_msg:
                             round_failed_models.add(model_id_for_stats)
                        elif "503" in error_msg or "Timeout" in error_msg:
                             round_failed_models.add(model_id_for_stats)

                        last_error = e
                        last_stack_trace = traceback.format_exc()
                        
                        retry_count += 1
                        continue
                    # === 尝试模型的代码结束 ===
        else:
            # 自适应/随机模式：最多尝试 max_attempts 个不同的模型
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"[模型选择] {strategy.upper()}模式 | 最大尝试次数: {max_attempts}")
            logger.info("=" * 60)
            
            attempt_idx = 0
            for model_item in models:
                if attempt_idx >= max_attempts:
                    logger.info(f"  ⚠️ 已达到最大尝试次数 {max_attempts}，停止尝试")
                    break
                    
                attempt_idx += 1
                normalized = self._normalize_model_entry(model_item)
                model_name = normalized["model"]
                provider_id = normalized["provider"]
                model_id_for_stats = self._extract_model_id(model_item)
                
                provider_tag = f"[{provider_id}]"
                
                logger.info(f"  ┌──────────────────────────────────────────────")
                logger.info(f"  │ 🧪 尝试 {attempt_idx}/{max_attempts}: {provider_tag} {model_name}")
                logger.info(f"  │    统计ID: {model_id_for_stats}")
                
                if model_id_for_stats in excluded_models:
                    logger.info(f"  │ ❌ 跳过: 排除列表")
                    logger.info(f"  └──────────────────────────────────────────────")
                    continue
                
                stats = self._get_model_stats(model_id_for_stats)
                if stats.get("cooldown_until", 0) > time.time():
                    cooldown_remaining = int(stats["cooldown_until"] - time.time())
                    logger.info(f"  │ ❌ 跳过: 冷却中 (剩余 {cooldown_remaining} 秒)")
                    logger.info(f"  └──────────────────────────────────────────────")
                    continue
                
                logger.info(f"  │ ✅ 通过检查，准备尝试...")
                logger.info(f"  └──────────────────────────────────────────────")

                try:
                    # Resolve Provider
                    target_model_id = model_name
                    target_base_url = config.providers.upstream.base_url
                    target_api_key = config.providers.upstream.api_key
                    target_protocol = getattr(config.providers.upstream, "protocol", "openai")
                    # Default to upstream verify_ssl (fallback to True if missing in config object)
                    target_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)
                    provider_label = None
                    
                    # Check if we are using a custom provider
                    if provider_id != "upstream":
                        if provider_id in config.providers.custom:
                            provider = config.providers.custom[provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_protocol = getattr(provider, "protocol", "openai")
                            target_verify_ssl = getattr(provider, "verify_ssl", True)
                            provider_label = provider_id
                        else:
                            logger.warning(f"Provider '{provider_id}' not found for model '{model_name}'. Using default upstream.")
                            pass 

                    # Check model_provider_map (for compatibility)
                    elif model_name in config.providers.map:
                        mapped_provider_id = config.providers.map[model_name]
                        if mapped_provider_id in config.providers.custom:
                            provider = config.providers.custom[mapped_provider_id]
                            target_base_url = provider.base_url
                            target_api_key = provider.api_key
                            target_protocol = getattr(provider, "protocol", "openai")
                            target_verify_ssl = getattr(provider, "verify_ssl", True)
                            provider_label = mapped_provider_id
                        else:
                             logger.warning(f"Mapped provider '{provider_id}' not found for model '{model_name}'. Using default upstream.")

                    # Construct Display Model Name (Provider/Model)
                    if provider_label:
                        display_model_name = f"{provider_label}/{target_model_id}"
                    else:
                        # 对于 upstream 提供商，使用 "upstream" 作为前缀，便于在日志中识别
                        display_model_name = f"upstream/{target_model_id}"

                    # 2. Log: Model Call Start
                    call_start_time = time.time()
                    # Fix: Duration should be relative to previous step or just 0?
                    # The prompt says: "框架接收→首次调用"
                    # So duration_since_req is correct for "Framework Received -> First Call".
                    
                    duration_since_req = (call_start_time - start_time) * 1000
                    trace_logger.log(trace_id, "MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, details=f"正在尝试: {display_model_name}")
                    
                    add_trace_event("MODEL_CALL_START", call_start_time, duration_since_req, "success", retry_count, model=display_model_name)
                    
                    logger.info("")
                    logger.info("  " + "─" * 56)
                    logger.info(f"  📤 正在请求: {display_model_name}")
                    logger.info(f"     提供商URL: {target_base_url}")
                    logger.info("  " + "─" * 56)
                    
                    has_images = self._has_image_content(request.messages)
                    model_multimodal = normalized.get("multimodal", True)
                    
                    processed_request = request
                    log_messages = request.messages
                    if has_images:
                        if not model_multimodal:
                            logger.info(f"  [图片处理] 检测到图片内容，但模型不支持多模态。开始图片转述...")
                            image_start_time = time.time()
                            add_trace_event("IMAGE_TRANSCRIBE_START", image_start_time, 0, "success", retry_count)
                            
                            processed_messages = await self._process_messages_with_images(
                                request.messages, 
                                preserve_original=False
                            )
                            processed_request = ChatCompletionRequest(
                                model=request.model,
                                messages=processed_messages,
                                temperature=request.temperature,
                                top_p=request.top_p,
                                n=request.n,
                                stream=request.stream,
                                stop=request.stop,
                                max_tokens=request.max_tokens,
                                presence_penalty=request.presence_penalty,
                                frequency_penalty=request.frequency_penalty,
                                logit_bias=request.logit_bias,
                                user=request.user,
                                tools=request.tools,
                                tool_choice=request.tool_choice,
                                response_format=request.response_format
                            )
                            log_messages = processed_messages
                            
                            image_end_time = time.time()
                            image_duration = (image_end_time - image_start_time) * 1000
                            add_trace_event("IMAGE_TRANSCRIBE_DONE", image_end_time, image_duration, "success", retry_count)
                            logger.info(f"  [图片处理] 图片转述完成，准备发送请求")
                        else:
                            logger.info(f"  [图片处理] 检测到图片内容，模型支持多模态。先描述图片以缓存，然后保留原始图片...")
                            image_start_time = time.time()
                            add_trace_event("IMAGE_CACHE_START", image_start_time, 0, "success", retry_count)
                            
                            processed_messages = await self._process_messages_with_images(
                                request.messages, 
                                preserve_original=True
                            )
                            processed_request = ChatCompletionRequest(
                                model=request.model,
                                messages=processed_messages,
                                temperature=request.temperature,
                                top_p=request.top_p,
                                n=request.n,
                                stream=request.stream,
                                stop=request.stop,
                                max_tokens=request.max_tokens,
                                presence_penalty=request.presence_penalty,
                                frequency_penalty=request.frequency_penalty,
                                logit_bias=request.logit_bias,
                                user=request.user,
                                tools=request.tools,
                                tool_choice=request.tool_choice,
                                response_format=request.response_format
                            )
                            log_messages = processed_messages
                            
                            image_end_time = time.time()
                            image_duration = (image_end_time - image_start_time) * 1000
                            add_trace_event("IMAGE_CACHE_DONE", image_end_time, image_duration, "success", retry_count)
                            logger.info(f"  [图片处理] 图片描述缓存完成，保留原始图片")
                    
                    response_data = await self._call_upstream(processed_request, target_model_id, target_base_url, target_api_key, timeout_ms, stream_timeout_ms, trace_id, retry_count, call_start_time, add_trace_event, protocol=target_protocol, verify_ssl=target_verify_ssl)
                    
                    # Record Success for Adaptive Routing
                    self._record_success(model_id_for_stats)

                    # 3. Log: Full Response (Success)
                    end_time = time.time()
                    duration = (end_time - start_time) * 1000
                    
                    # Record response time for Adaptive Routing
                    self._record_response_time(model_id_for_stats, duration)
                    
                    # Extract usage if available
                    token_source = "upstream"
                    if "usage" in response_data:
                         usage = response_data["usage"]
                         prompt_tokens = usage.get("prompt_tokens", 0)
                         completion_tokens = usage.get("completion_tokens", 0)
                    else:
                         token_source = "local"
                         prompt_tokens = 0
                         completion_tokens = 0
                         if "usage" not in response_data:
                             req_messages = request.messages
                             prompt_tokens = self._count_messages_tokens(req_messages, model_name)
                             completion_content = ""
                             if "choices" in response_data and response_data["choices"]:
                                 completion_content = response_data["choices"][0]["message"].get("content", "")
                             completion_tokens = self._count_tokens(completion_content, model_name)

                    # 🎉 成功响应的美观日志
                    logger.info("")
                    logger.info("  " + "─" * 56)
                    logger.info(f"  ✅ 请求成功!")
                    logger.info(f"  🤖 使用模型: {display_model_name}")
                    logger.info(f"  ⏱️  总耗时: {duration:.1f}ms")
                    logger.info(f"  📊 Token使用: {prompt_tokens} + {completion_tokens} = {prompt_tokens + completion_tokens}")
                    logger.info("  " + "─" * 56)
                    logger.info("")
                    logger.info("╔" + "═" * 58 + "╗")
                    logger.info("║" + " " * 18 + "🏁 请求完成" + " " * 30 + "║")
                    logger.info("╚" + "═" * 58 + "╝")
                    logger.info("")

                    # Log success (Async via BackgroundTasks)
                    background_tasks.add_task(
                        self._log_request,
                        level, display_model_name, duration, "success", 
                        self._extract_text_from_content(log_messages[-1].get("content")) if log_messages else user_prompt, 
                        json.dumps({**request.model_dump(), "messages": log_messages}), 
                        json.dumps(response_data), 
                        trace_events, None, retry_count, prompt_tokens, completion_tokens, token_source
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

                    # ❌ 模型失败的美观日志
                    logger.info("")
                    logger.info("  " + "─" * 56)
                    logger.info(f"  ❌ 模型请求失败")
                    logger.info(f"  🤖 模型: {display_model_name}")
                    logger.info(f"  ⚠️  原因: {reason}")
                    logger.info(f"  ⏱️  耗时: {fail_duration:.1f}ms")
                    if cooldown > 0:
                        logger.info(f"  🕒  冷却: {cooldown}秒")
                    logger.info("  " + "─" * 56)
                    
                    trace_logger.log(trace_id, "MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, details=f"原因: {reason} | 模型: {display_model_name}")
                    add_trace_event("MODEL_FAIL", fail_time, fail_duration, "fail", retry_count, model=display_model_name, reason=reason)
                    
                    # Record Failure for Adaptive Routing with calculated penalty and cooldown
                    self._record_failure(model_id_for_stats, penalty=penalty, cooldown_seconds=cooldown)

                    # Accumulate error history
                    detailed_error = f"[Attempt {attempt_idx}|{display_model_name}] {reason}"
                    if str(e) != reason:
                         detailed_error += f" ({str(e)})"
                    attempt_errors.append(detailed_error)

                    # Strategy: 
                    # 1. Hard Failures (Auth, Client Error) -> Exclude for entire request
                    if "401" in error_msg or "403" in error_msg or "404" in error_msg:
                         excluded_models.add(model_id_for_stats)
                    # 2. Rate Limit (429) -> Exclude for entire request to avoid spamming
                    elif "429" in error_msg:
                         excluded_models.add(model_id_for_stats)

                    last_error = e
                    last_stack_trace = traceback.format_exc()
                    
                    # Increment retry count ONLY after full processing of failure
                    retry_count += 1
                    continue
                
        # All failed
        duration = (time.time() - start_time) * 1000
        
        # 💥 所有模型失败的美观日志
        logger.info("")
        logger.info("╔" + "═" * 58 + "╗")
        logger.info("║" + " " * 15 + "💥 所有模型失败" + " " * 31 + "║")
        logger.info("╚" + "═" * 58 + "╝")
        logger.info(f"📊 尝试次数: {retry_count}")
        logger.info(f"⏱️  总耗时: {duration:.1f}ms")
        logger.info("")
        
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
        if protocol == "v1-messages" or protocol == "v1-response":
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
        if protocol == "v1-messages" or protocol == "v1-response":
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

        # Handle v1-response Protocol (No Stream, /v1/responses endpoint)
        if protocol == "v1-response":
             # Convert OpenAI messages to v1/responses format
             base = base_url.rstrip('/')
             url = f"{base}/responses"
             
             # 创建 v1/responses 格式的 payload
             v1_response_payload = {
                 "model": payload.get("model")
             }
             
             # 转换 messages 为 input 格式
             # v1/responses 的 input 是完整的消息列表
             messages = payload.get("messages", [])
             if messages:
                 converted_messages = []
                 for msg in messages:
                     role = msg.get("role")
                     content = msg.get("content")
                     tool_calls = msg.get("tool_calls")
                     tool_call_id = msg.get("tool_call_id")
                     
                     if role == "system":
                         # system 消息在 v1/responses 中使用 instructions 字段
                         v1_response_payload["instructions"] = self._extract_text_from_content(content)
                         continue
                     
                     if role == "tool":
                         # 工具调用结果
                         # v1/responses 格式: {"type": "function_call_output", "call_id": "...", "output": "..."}
                         converted_msg = {
                             "type": "function_call_output",
                             "call_id": tool_call_id,
                             "output": self._extract_text_from_content(content)
                         }
                         converted_messages.append(converted_msg)
                     elif role == "assistant":
                         # 助手消息，可能包含 tool_calls
                         if tool_calls:
                             # 转换 tool_calls 为 function_call 格式
                             for tc in tool_calls:
                                 func = tc.get("function", {})
                                 converted_msg = {
                                     "type": "function_call",
                                     "id": tc.get("id"),
                                     "name": func.get("name"),
                                     "arguments": func.get("arguments")
                                 }
                                 converted_messages.append(converted_msg)
                         if content:
                             # 文本内容
                             converted_msg = {
                                 "role": "assistant",
                                 "content": self._convert_content_to_v1_response(content, "output")
                             }
                             converted_messages.append(converted_msg)
                     elif role == "user":
                         # 用户消息
                         converted_msg = {
                             "role": "user",
                             "content": self._convert_content_to_v1_response(content, "input")
                         }
                         converted_messages.append(converted_msg)
                 
                 v1_response_payload["input"] = converted_messages
             
             # 转换 tools 参数
             if "tools" in payload:
                 v1_tools = []
                 for tool in payload["tools"]:
                     if tool.get("type") == "function":
                         func = tool.get("function", {})
                         v1_tools.append({
                             "type": "function",
                             "name": func.get("name"),
                             "description": func.get("description", ""),
                             "parameters": func.get("parameters", {})
                         })
                 if v1_tools:
                     v1_response_payload["tools"] = v1_tools
             
             # 传递其他参数
             if "max_tokens" in payload:
                 v1_response_payload["max_output_tokens"] = payload["max_tokens"]
             if "temperature" in payload:
                 v1_response_payload["temperature"] = payload["temperature"]
             if "top_p" in payload:
                 v1_response_payload["top_p"] = payload["top_p"]
             if "response_format" in payload:
                 # v1/responses 使用 text.format 字段
                 rf = payload["response_format"]
                 if rf.get("type") == "json_object":
                     v1_response_payload["text"] = {"format": {"type": "json_object"}}
                 elif rf.get("type") == "json_schema":
                     v1_response_payload["text"] = {"format": rf}
             
             # 使用转换后的 payload
             payload = v1_response_payload
             
             try:
                # FORCE DISABLE SSL VERIFICATION as requested by user
                verify_ssl = False
                
                temp_client = httpx.AsyncClient(verify=False, timeout=timeout_config)
                client_to_use = temp_client
                    
                try:
                    logger.info(f"Upstream Request (v1-response): {url} (SSL Disabled)")
                    response = await client_to_use.post(url, json=payload, headers=headers, timeout=timeout_config)
                finally:
                    if temp_client:
                        await temp_client.aclose()
                 
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
                
                # 转换 v1/responses 响应格式为 OpenAI chat.completions 兼容格式
                if "choices" not in response_data:
                    content_text = ""
                    tool_calls = []
                    
                    # v1/responses 格式分析
                    # output 包含 message 类型和 function_call 类型
                    if "output" in response_data:
                        output = response_data["output"]
                        if isinstance(output, list):
                            for item in output:
                                if isinstance(item, dict):
                                    item_type = item.get("type")
                                    
                                    if item_type == "message":
                                        # 消息类型，提取 content
                                        msg_content = item.get("content", [])
                                        if isinstance(msg_content, list):
                                            for c in msg_content:
                                                if isinstance(c, dict) and c.get("type") == "output_text":
                                                    content_text += c.get("text", "")
                                        elif isinstance(msg_content, str):
                                            content_text += msg_content
                                    
                                    elif item_type == "function_call":
                                        # 函数调用类型
                                        args = item.get("arguments")
                                        if isinstance(args, dict):
                                            args = json.dumps(args)
                                        tool_call = {
                                            "id": item.get("id", f"call_{int(time.time())}"),
                                            "type": "function",
                                            "function": {
                                                "name": item.get("name", ""),
                                                "arguments": args or "{}"
                                            }
                                        }
                                        tool_calls.append(tool_call)
                                    
                                    elif item_type == "output_text":
                                        # 直接输出文本（旧格式兼容）
                                        content_text += item.get("text", "")
                                        
                        elif isinstance(output, str):
                            content_text = output
                    
                    # 构造 Message 对象
                    message_obj = {
                        "role": "assistant",
                        "content": content_text if content_text else None
                    }
                    if tool_calls:
                        message_obj["tool_calls"] = tool_calls
                    
                    # 获取 usage 信息
                    prompt_tokens = self._count_messages_tokens(request.messages, model_id)
                    completion_tokens = self._count_tokens(content_text, model_id)
                    
                    if "usage" in response_data:
                        usage = response_data["usage"]
                        if "input_tokens" in usage:
                            prompt_tokens = usage["input_tokens"]
                        if "output_tokens" in usage:
                            completion_tokens = usage["output_tokens"]
                    
                    # 构造 OpenAI 格式响应
                    mapped_response = {
                        "id": response_data.get("id", f"chatcmpl-{int(time.time())}"),
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": response_data.get("model", model_id),
                        "choices": [
                            {
                                "index": 0,
                                "message": message_obj,
                                "finish_reason": "tool_calls" if tool_calls else (response_data.get("status", "stop") or "stop")
                            }
                        ],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens
                        }
                    }
                        
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
                 # Handle SSL verification logic manually since httpx.post doesn't support 'verify' arg
                
                # FORCE DISABLE SSL VERIFICATION as requested by user (v1-messages)
                verify_ssl = False
                
                temp_client = httpx.AsyncClient(verify=False, timeout=timeout_config)
                client_to_use = temp_client
                    
                try:
                    logger.info(f"Upstream Request (v1-messages): {url} (SSL Disabled)")
                    response = await client_to_use.post(url, json=payload, headers=headers, timeout=timeout_config)
                finally:
                    if temp_client:
                        await temp_client.aclose()
                 
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
            
            # Determine which client to use based on verify_ssl requirement
            temp_client = None
            client_to_use = self._client
            
            # FORCE DISABLE SSL VERIFICATION as requested by user (stream)
            verify_ssl = False
            
            # Create a temporary client with verify=False
            # Inherit global limits if possible, but for temp usage default is fine
            temp_client = httpx.AsyncClient(verify=False, timeout=timeout_config)
            client_to_use = temp_client
            
            try:
                base_url_stream = base_url.rstrip('/')
                # Prevent double path appending
                if base_url_stream.endswith("/chat/completions"):
                    url_stream = base_url_stream
                elif base_url_stream.endswith("/"):
                    url_stream = f"{base_url_stream}chat/completions"
                else:
                    url_stream = f"{base_url_stream}/chat/completions"
                    
                logger.info(f"Upstream Request (Stream): {url_stream} (SSL Disabled)")
                
                # Do NOT pass verify=... to stream(), as it's not supported in all versions/modes
                ctx = client_to_use.stream("POST", url_stream, json=payload, headers=headers, timeout=timeout_config)
                
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
            
            finally:
                if temp_client:
                    await temp_client.aclose()

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
                    token_source=token_source,
                    category=category
                )
                session.add(log_entry)
                await session.commit()
                
                from database import update_daily_stats
                await update_daily_stats(log_entry)
            except Exception as e:
                logger.error(f"Failed to log request: {e}")

    async def test_model_connection(self, model_item: Any) -> Dict[str, Any]:
        """Test if a model is available and responsive."""
        normalized = self._normalize_model_entry(model_item)
        model_name = normalized["model"]
        provider_id = normalized["provider"]
        
        config = config_manager.get_config()
        
        target_base_url = config.providers.upstream.base_url
        target_api_key = config.providers.upstream.api_key
        target_protocol = getattr(config.providers.upstream, "protocol", "openai")
        target_verify_ssl = getattr(config.providers.upstream, "verify_ssl", True)
        
        if provider_id != "upstream":
            if provider_id in config.providers.custom:
                provider = config.providers.custom[provider_id]
                target_base_url = provider.base_url
                target_api_key = provider.api_key
                target_protocol = getattr(provider, "protocol", "openai")
                target_verify_ssl = getattr(provider, "verify_ssl", True)
            else:
                return {
                    "success": False,
                    "error": f"Provider '{provider_id}' not found"
                }
        
        try:
            headers = {
                "Authorization": f"Bearer {target_api_key}",
                "Content-Type": "application/json"
            }
            
            timeout_config = httpx.Timeout(
                connect=5.0,
                read=10.0,
                write=10.0,
                pool=10.0
            )
            
            test_payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5
            }
            
            if target_protocol == "v1-messages":
                test_payload["stream"] = False
                url = f"{target_base_url.rstrip('/')}/messages"
            elif target_protocol == "v1-response":
                test_payload["stream"] = False
                # 转换为 v1/responses 格式
                v1_response_payload = {
                    "model": model_name,
                    "input": "Hi",
                    "max_output_tokens": 5
                }
                test_payload = v1_response_payload
                url = f"{target_base_url.rstrip('/')}/responses"
            else:
                test_payload["stream"] = False
                url = f"{target_base_url.rstrip('/')}/chat/completions"
            
            temp_client = httpx.AsyncClient(verify=target_verify_ssl, timeout=timeout_config)
            try:
                start_time = time.time()
                response = await temp_client.post(url, json=test_payload, headers=headers, timeout=timeout_config)
                duration_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "duration_ms": duration_ms,
                        "status_code": response.status_code
                    }
                else:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": response.text
                    }
            finally:
                await temp_client.aclose()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

router_engine = RouterEngine()
