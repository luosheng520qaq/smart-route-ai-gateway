import json
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class RouterModelConfig(BaseModel):
    enabled: bool = False
    model: str = "gpt-3.5-turbo"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    prompt_template: str = """You are an intent router for an advanced AI Agent system.
Analyze the user's request history and classify the complexity into one of three levels based on **Reasoning Depth** and **Tool/System Interaction**.

**Guidelines:**
- **Short does NOT mean simple.** A request like "Restart the server" is short but requires high-privilege tool access (T2/T3).
- **Tool usage rules out T1.** If the user implies ANY action beyond pure conversation (e.g., searching, clicking, file manipulation), it must be T2 or T3.

**Classification Levels:**

T1 (Passive / Text-Only):
- Pure conversation, greetings, chit-chat.
- Factual questions answerable by internal knowledge (e.g., "What is the capital of France?").
- **Constraint:** NO external tools, NO system operations, NO side effects.

T2 (Active / Single-Task):
- Requests requiring **Standard Tool Usage** (e.g., Web Search, Calculator, Weather).
- Code generation (Functions, scripts).
- Simple system operations (e.g., "Open the browser", "Create a folder").
- Analysis of user-provided files/images.

T3 (Agentic / Complex Flow):
- **Complex Agent Workflows:** Multi-step executions (e.g., "Go to GitHub, find the repo, clone it, and fix the bug").
- **Deep System Control:** Automating browser interaction (Selenium/Playwright), OS-level modifications.
- High-stakes reasoning, architectural design, or handling ambiguous instructions that require planning.

User History:
{history}

Respond ONLY with the label: "T1", "T2", or "T3"."""

class RetryConfig(BaseModel):
    status_codes: List[int] = [429, 500, 502, 503, 504]
    error_keywords: List[str] = ["rate limit", "quota exceeded", "overloaded", "timeout", "try again"]

class ProviderConfig(BaseModel):
    base_url: str
    api_key: str

class AppConfig(BaseModel):
    t1_models: List[str] = ["gpt-3.5-turbo", "gpt-4o-mini"]
    t2_models: List[str] = ["gpt-4", "gpt-4-turbo"]
    t3_models: List[str] = ["gpt-4-32k", "claude-3-opus"]
    timeouts: Dict[str, int] = {"t1": 5000, "t2": 15000, "t3": 30000}
    
    # Default upstream (Legacy or Default Provider)
    upstream_base_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""
    
    gateway_api_key: str = "" # Key required to access this gateway
    
    # New configurations
    router_config: RouterModelConfig = RouterModelConfig()
    retry_config: RetryConfig = RetryConfig()
    log_retention_days: int = 7 # Default keep logs for 7 days
    
    # Global and Model-specific parameter overrides
    # global_params applies to all models if not specified in request
    global_params: Dict[str, Any] = {} 
    # model_params: key is model_name, value is dict of params (e.g. {"gpt-4": {"top_p": 0.5}})
    model_params: Dict[str, Dict[str, Any]] = {}
    
    # Multi-Provider Configuration
    # providers: key is provider_id (e.g. "azure"), value is config
    providers: Dict[str, ProviderConfig] = {}
    # model_provider_map: key is model_name, value is provider_id
    # e.g. {"gpt-4": "azure", "claude-3": "anthropic"}
    model_provider_map: Dict[str, str] = {}

class ConfigManager:
    _instance = None
    _config: AppConfig = None
    _config_path: str = "config.json"

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
                    self._config = AppConfig(**data)
            except Exception as e:
                print(f"Error loading config, using default: {e}")
                self._config = AppConfig()
        else:
            self._config = AppConfig()
            self.save_config()

    def save_config(self):
        with open(self._config_path, 'w', encoding='utf-8') as f:
            f.write(self._config.model_dump_json(indent=2))

    def get_config(self) -> AppConfig:
        return self._config

    def update_config(self, new_config: dict):
        # Merge updates
        current_data = self._config.model_dump()
        current_data.update(new_config)
        self._config = AppConfig(**current_data)
        self.save_config()

config_manager = ConfigManager()
