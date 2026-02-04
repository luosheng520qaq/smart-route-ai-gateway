import axios from 'axios';

export const api = axios.create({
  baseURL: (import.meta as any).env.VITE_API_URL || '',
});

// Interceptor to add Bearer token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
    response => response,
    error => {
        if (error.response?.status === 401 && !window.location.pathname.includes('/login')) {
            // Optional: Redirect to login or clear token
            // But let the component handle it via AuthContext
        }
        return Promise.reject(error);
    }
);

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
  retry_on_empty: boolean;
}

export interface HealthCheckConfig {
  decay_rate: number;
}

export interface ProviderConfig {
  base_url: string;
  api_key: string;
}

export interface GeneralConfig {
  log_retention_days: number;
  gateway_api_key: string;
}

export interface ModelsConfig {
  t1: string[];
  t2: string[];
  t3: string[];
  strategies: Record<string, string>;
}

export interface TimeoutConfig {
  connect: Record<string, number>;
  generation: Record<string, number>;
}

export interface RetrySettings {
  rounds: Record<string, number>;
  max_retries: Record<string, number>;
  conditions: RetryConfig;
}

export interface UpstreamConfig {
    base_url: string;
    api_key: string;
}

export interface ProvidersConfig {
  upstream: UpstreamConfig;
  custom: Record<string, ProviderConfig>;
  map: Record<string, string>;
}

export interface ParameterConfig {
  global_params: Record<string, any>;
  model_params: Record<string, Record<string, any>>;
}

export interface AppConfig {
  general: GeneralConfig;
  models: ModelsConfig;
  timeouts: TimeoutConfig;
  retries: RetrySettings;
  providers: ProvidersConfig;
  router: RouterConfig;
  health: HealthCheckConfig;
  params: ParameterConfig;
}

export interface ConfigHistory {
    id: number;
    timestamp: string;
    config_json: string;
    change_reason: string;
    user: string;
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
  prompt_tokens?: number;
  completion_tokens?: number;
  token_source?: string;
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
  request_change_percentage?: number;
  avg_duration: number;
  error_rate: number;
  intent_distribution: { name: string; value: number }[];
  response_trend: { time: string; duration: number }[];
  tokens?: {
      prompt: number;
      completion: number;
      total: number;
  };
}

export const fetchStats = async (range: 'today' | '3days' | 'all' = 'today') => {
  const response = await api.get<Stats>(`/api/stats?range=${range}`);
  return response.data;
};

export const fetchConfig = async () => {
  const response = await api.get<AppConfig>('/api/config');
  return response.data;
};

export const updateConfig = async (config: AppConfig) => {
  const response = await api.post('/api/config', config);
  return response.data;
};

export const fetchHistory = async (limit = 10) => {
    const response = await api.get<ConfigHistory[]>(`/api/config/history?limit=${limit}`);
    return response.data;
}

export const rollbackConfig = async (historyId: number) => {
    const response = await api.post<{status: string, message: string, config: AppConfig}>('/api/config/rollback', { history_id: historyId });
    return response.data;
}

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

export const fetchModelStats = async () => {
  const response = await api.get<Record<string, { failures: number; success: number; failure_score?: number; health_score?: number }>>('/api/stats/models');
  return response.data;
};
