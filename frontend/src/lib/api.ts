import axios from 'axios';

const API_BASE_URL = ''; // Use relative path for portability

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add Auth Interceptor
api.interceptors.request.use((config) => {
  const key = localStorage.getItem('gateway_key');
  if (key) {
    config.headers.Authorization = `Bearer ${key}`;
  }
  return config;
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
  routing_strategies: Record<string, string>; // New field: t1/t2/t3 -> sequential/random/adaptive
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
  trace?: string; // JSON string of TraceEvent[]
  stack_trace?: string;
  retry_count?: number;
}

export interface TraceEvent {
  stage: string;
  timestamp: number;
  duration_ms: number;
  status: string;
  retry_count: number;
  model?: string;
  reason?: string;
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

export interface LogFilters {
  level?: string;
  status?: string;
  model?: string;
  start_date?: string;
  end_date?: string;
}

export const fetchLogs = async (page = 1, pageSize = 20, filters: LogFilters = {}) => {
  const params = new URLSearchParams();
  params.append('page', page.toString());
  params.append('page_size', pageSize.toString());
  
  if (filters.level && filters.level !== 'all') params.append('level', filters.level);
  if (filters.status && filters.status !== 'all') params.append('status', filters.status);
  if (filters.model) params.append('model', filters.model);
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  
  const response = await api.get<{ logs: RequestLog[]; total: number; page: number }>(`/api/logs?${params.toString()}`);
  return response.data;
};

export const exportLogs = async (filters: LogFilters = {}) => {
  const params = new URLSearchParams();
  if (filters.level && filters.level !== 'all') params.append('level', filters.level);
  if (filters.status && filters.status !== 'all') params.append('status', filters.status);
  if (filters.model) params.append('model', filters.model);
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  
  const response = await api.get(`/api/logs/export?${params.toString()}`, {
    responseType: 'blob',
  });
  return response.data;
};

export const fetchStats = async () => {
  const response = await api.get<Stats>('/api/stats');
  return response.data;
};

export const fetchModelStats = async () => {
  const response = await api.get<Record<string, { failures: number; success: number }>>('/api/stats/models');
  return response.data;
};
