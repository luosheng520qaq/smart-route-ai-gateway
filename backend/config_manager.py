import json
import os
import shutil
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# --- Functional Module Configs ---

class GeneralConfig(BaseModel):
    log_retention_days: int = 7
    gateway_api_key: str = ""

class ModelsConfig(BaseModel):
    t1: List[str] = ["gpt-3.5-turbo", "gpt-4o-mini"]
    t2: List[str] = ["gpt-4", "gpt-4-turbo"]
    t3: List[str] = ["gpt-4-32k", "claude-3-opus"]
    strategies: Dict[str, str] = {"t1": "sequential", "t2": "sequential", "t3": "sequential"}

class TimeoutConfig(BaseModel):
    connect: Dict[str, int] = {"t1": 5000, "t2": 15000, "t3": 30000} # TTFT
    generation: Dict[str, int] = {"t1": 300000, "t2": 300000, "t3": 300000} # Total

class RetryConfig(BaseModel):
    status_codes: List[int] = [429, 500, 502, 503, 504]
    error_keywords: List[str] = ["rate limit", "quota exceeded", "overloaded", "timeout", "try again"]
    retry_on_empty: bool = True

class RetrySettings(BaseModel):
    rounds: Dict[str, int] = {"t1": 1, "t2": 1, "t3": 1}
    max_retries: Dict[str, int] = {"t1": 3, "t2": 3, "t3": 3}
    conditions: RetryConfig = RetryConfig()

class RouterModelConfig(BaseModel):
    enabled: bool = False
    model: str = "gpt-3.5-turbo"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    verify_ssl: bool = True
    prompt_template: str = """You are an intelligent router for an LLM system. Your job is to classify the USER'S INTENT into one of three tiers (T1, T2, T3) to select the most appropriate model.
    
**TIER DEFINITIONS:**

**T1 (Speed / Chat / Simple QA)**:
- Casual conversation, greetings, roleplay.
- Simple factual questions (e.g., "Who is Newton?", "Translate this").
- Summary of short text provided in context.
- **Key:** Low reasoning depth, no external tools needed, safe for smaller/faster models.

**T2 (Reasoning / Coding / Tools)**:
- **Coding:** Writing code, debugging, explaining complex code, SQL queries.
- **Reasoning:** Logic puzzles, math problems, complex analysis.
- **Tool Use:** Explicit requests to search the web, check weather, read files.
- **Creative Writing:** Long stories, detailed emails, nuances.
- **Key:** Requires capabilities of GPT-4/Claude-3.5-Sonnet level models.

**T3 (Complex Agentic / Deep Logic)**:
- **Multi-step Complex Tasks:** "Research topic X, write a report, and save it to a file."
- **Deep Architecting:** System design, complex project planning.
- **High Risk:** Sensitive operations requiring maximum intelligence and safety.
- **Key:** Requires SOTA models (o1, Claude-3-Opus).

**INPUT CONTEXT (User History):**
{history}

**INSTRUCTIONS:**
1. Analyze the *latest* user request in the context of the history.
2. If the user asks for code, IT IS T2.
3. If the user asks for search/internet, IT IS T2.
4. If it's simple chat, IT IS T1.
5. Respond ONLY with the label: "T1", "T2", or "T3"."""

class HealthCheckConfig(BaseModel):
    decay_rate: float = 0.05 # Recovery points per minute

class SecurityConfig(BaseModel):
    access_token_expire_minutes: int = 1440 # 24 hours

class ProviderConfig(BaseModel):
    base_url: str
    api_key: str
    protocol: str = "openai" # openai, v1-messages
    verify_ssl: bool = True

class UpstreamConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    verify_ssl: bool = True

class ProvidersConfig(BaseModel):
    upstream: UpstreamConfig = UpstreamConfig()
    custom: Dict[str, ProviderConfig] = {}
    map: Dict[str, str] = {} # model_provider_map

class ParameterConfig(BaseModel):
    global_params: Dict[str, Any] = {}
    model_params: Dict[str, Dict[str, Any]] = {}

# --- Main App Config ---

class AppConfig(BaseModel):
    general: GeneralConfig = GeneralConfig()
    security: SecurityConfig = SecurityConfig()
    models: ModelsConfig = ModelsConfig()
    timeouts: TimeoutConfig = TimeoutConfig()
    retries: RetrySettings = RetrySettings()
    providers: ProvidersConfig = ProvidersConfig()
    router: RouterModelConfig = RouterModelConfig()
    health: HealthCheckConfig = HealthCheckConfig()
    params: ParameterConfig = ParameterConfig()

    # Compatibility Properties (Read-Only helpers for code migration)
    # Note: These help reading, but writing to config.t1_models won't work as expected if Pydantic model is immutable or if we assign.
    # Ideally, we should update the codebase references.
    
    @property
    def t1_models(self): return self.models.t1
    @property
    def t2_models(self): return self.models.t2
    @property
    def t3_models(self): return self.models.t3
    @property
    def routing_strategies(self): return self.models.strategies
    @property
    def log_retention_days(self): return self.general.log_retention_days
    @property
    def gateway_api_key(self): return self.general.gateway_api_key
    @property
    def upstream_base_url(self): return self.providers.upstream.base_url
    @property
    def upstream_api_key(self): return self.providers.upstream.api_key
    @property
    def retry_rounds(self): return self.retries.rounds
    @property
    def retry_config(self): return self.retries.conditions
    @property
    def stream_timeouts(self): return self.timeouts.generation
    @property
    def global_params(self): return self.params.global_params
    @property
    def model_params(self): return self.params.model_params
    @property
    def model_provider_map(self): return self.providers.map
    @property
    def health_check_config(self): return self.health
    @property
    def router_config(self): return self.router

class ConfigManager:
    _instance = None
    _config: AppConfig = None
    # 使用 backend 目录下的配置文件，避免与根目录冲突
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    _config_path: str = os.path.join(_base_dir, "config.json")
    _backup_path: str = os.path.join(_base_dir, "config.backup.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self):
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Check for migration
                if "t1_models" in data:
                    print("[INFO] Detected legacy config format. Migrating...")
                    self._migrate_config(data)
                else:
                    self._config = AppConfig(**data)
            except Exception as e:
                print(f"[ERROR] Error loading config, using default: {e}")
                self._config = AppConfig()
        else:
            self._config = AppConfig()
            self.save_config()

    def _migrate_config(self, old_data: dict):
        """Migrate flat config to nested structure."""
        # Backup first
        try:
            shutil.copy2(self._config_path, self._backup_path)
            print(f"[INFO] Backup created at {self._backup_path}")
        except Exception as e:
            print(f"[WARN] Failed to backup config: {e}")

        new_config = AppConfig()
        
        # General
        new_config.general.log_retention_days = old_data.get("log_retention_days", 7)
        new_config.general.gateway_api_key = old_data.get("gateway_api_key", "")
        
        # Models
        new_config.models.t1 = old_data.get("t1_models", new_config.models.t1)
        new_config.models.t2 = old_data.get("t2_models", new_config.models.t2)
        new_config.models.t3 = old_data.get("t3_models", new_config.models.t3)
        new_config.models.strategies = old_data.get("routing_strategies", new_config.models.strategies)
        
        # Timeouts
        old_timeouts = old_data.get("timeouts", {})
        old_stream = old_data.get("stream_timeouts", {})
        new_config.timeouts.connect = old_timeouts if old_timeouts else new_config.timeouts.connect
        new_config.timeouts.generation = old_stream if old_stream else new_config.timeouts.generation
        
        # Retries
        new_config.retries.rounds = old_data.get("retry_rounds", new_config.retries.rounds)
        old_retry_conf = old_data.get("retry_config", {})
        if old_retry_conf:
             new_config.retries.conditions = RetryConfig(**old_retry_conf)
             
        # Providers
        new_config.providers.upstream.base_url = old_data.get("upstream_base_url", "https://api.openai.com/v1")
        new_config.providers.upstream.api_key = old_data.get("upstream_api_key", "")
        new_config.providers.custom = {k: ProviderConfig(**v) for k, v in old_data.get("providers", {}).items()}
        new_config.providers.map = old_data.get("model_provider_map", {})
        
        # Router
        old_router = old_data.get("router_config", {})
        if old_router:
            new_config.router = RouterModelConfig(**old_router)
            
        # Health
        old_health = old_data.get("health_check_config", {})
        if old_health:
            new_config.health = HealthCheckConfig(**old_health)
            
        # Params
        new_config.params.global_params = old_data.get("global_params", {})
        new_config.params.model_params = old_data.get("model_params", {})
        
        self._config = new_config
        self.save_config()
        print("[INFO] Config migration completed successfully.")

    def save_config(self):
        with open(self._config_path, 'w', encoding='utf-8') as f:
            f.write(self._config.model_dump_json(indent=2))

    def get_config(self) -> AppConfig:
        return self._config

    def update_config(self, new_config: dict):
        # Merge updates - Handling nested updates is tricky with pydantic
        # Easiest way: validate new dict against AppConfig, replace _config
        # Ensure we don't lose existing values if partial update (though usually full config is sent)
        
        # If partial update, we need deep merge. For now assume full config or compatible dict.
        # But wait, update_config in main.py does `config_manager.update_config(config.model_dump())`
        # So it passes the full new config structure.
        
        self._config = AppConfig(**new_config)
        self.save_config()

config_manager = ConfigManager()
