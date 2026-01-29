import axios from 'axios';

const API_BASE_URL = ''; // Use relative path for portability

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface RouterConfig {
  enabled: boolean;
  model: string;
  base_url: string;
  api_key: string;
  prompt_template: string;
}

export interface RetryConfig {
  status_codes: number[];
  error_keywords: string[];
}

export interface ProviderConfig {
  base_url: string;
  api_key: string;
}

export interface AppConfig {
  t1_models: string[];
  t2_models: string[];
  t3_models: string[];
  timeouts: Record<string, number>;
  stream_timeouts: Record<string, number>;
  retry_rounds: Record<string, number>;
  upstream_base_url: string;
  upstream_api_key: string;
  gateway_api_key: string; // New field
  router_config: RouterConfig;
  retry_config: RetryConfig;
  global_params: Record<string, any>;
  model_params: Record<string, Record<string, any>>;
  providers: Record<string, ProviderConfig>;
  model_provider_map: Record<string, string>;
}

export interface RequestLog {
  id: number;
  timestamp: string;
  level: string;
  model: string;
  duration_ms: number;
  status: string;
  user_prompt_preview: string;
  full_request: string;
  full_response: string;
}

export interface Stats {
  total_requests: number;
  avg_duration: number;
  error_rate: number;
  intent_distribution: { name: string; value: number }[];
  response_trend: { time: string; duration: number }[];
}

export const fetchConfig = async () => {
  const response = await api.get<AppConfig>('/api/config');
  return response.data;
};

export const updateConfig = async (config: AppConfig) => {
  const response = await api.post('/api/config', config);
  return response.data;
};

export const fetchLogs = async (page = 1, pageSize = 20) => {
  const response = await api.get<{ logs: RequestLog[]; total: number; page: number }>(`/api/logs?page=${page}&page_size=${pageSize}`);
  return response.data;
};

export const fetchStats = async () => {
  const response = await api.get<Stats>('/api/stats');
  return response.data;
};
