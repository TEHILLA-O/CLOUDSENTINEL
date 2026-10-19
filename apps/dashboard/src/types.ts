export interface Environment {
  id: string;
  name: string;
  provider: string;
  region: string;
  cluster_name: string;
  kubernetes_version: string | null;
  base_url: string;
  role: string;
  runtime: string;
  verification: string;
  experiments_allowed: boolean;
  enabled: boolean;
  notes: string;
  state: string;
  circuit: string;
  eligible: boolean;
  consecutive_failures: number;
  consecutive_successes: number;
  consecutive_latency_breaches: number;
  last_outcome: string | null;
  last_detail: string | null;
  last_latency_ms: number | null;
  last_checked_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Service {
  id: string;
  environment_id: string;
  name: string;
  analyse_path: string;
  base_url: string;
  state: string;
  eligible: boolean;
}

export interface Observation {
  id: number;
  checked_at: string;
  outcome: string;
  latency_ms: number;
  status_code: number | null;
  detail: string;
}

export interface IncidentEvent {
  id: number;
  occurred_at: string;
  kind: string;
  message: string;
  evidence: Record<string, unknown>;
}

export interface Incident {
  id: string;
  status: string;
  summary: string;
  trigger: string;
  started_at: string;
  detected_at: string;
  failure_window_started_at: string | null;
  routing_changed_at: string | null;
  resolved_at: string | null;
  duration_seconds: number | null;
  detection_seconds: number | null;
  preferred_environment_id: string | null;
  from_environment_id: string | null;
  to_environment_id: string | null;
  events: IncidentEvent[];
}

export interface Routing {
  active_environment_id: string | null;
  mode: string;
  manual_environment_id: string | null;
  preferred_environment_id: string | null;
  switched_at: string | null;
  cooldown_until: string | null;
  reason: string;
  generation: number;
  active_base_url: string | null;
  active_eligible: boolean;
  data_plane: string;
}

export interface Settings {
  health_check_interval_seconds: number;
  failure_threshold: number;
  success_threshold: number;
  cooldown_seconds: number;
  latency_threshold_ms: number;
  latency_breach_threshold: number;
  preferred_environment_id: string | null;
  alert_error_rate: number;
  alert_latency_ms: number;
  recovery_policy: string;
}

export interface MetricsSummary {
  window_seconds: number;
  request_count: number;
  error_count: number;
  error_rate: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  alert_error_rate: number;
  alert_latency_ms: number;
  by_environment: Array<{
    environment_id: string;
    request_count: number;
    error_count: number;
    latency_p50_ms: number;
  }>;
  series: Array<{
    minute: string;
    request_count: number;
    error_count: number;
    latency_p50_ms: number;
  }>;
  measurement: string;
}

export interface Meta {
  product: string;
  version: string;
  public_gateway_url: string;
  data_plane: string;
  dns_failover: boolean;
  limitations: string[];
}

export interface Experiment {
  id: string;
  kind: string;
  target_environment_id: string;
  status: string;
  requested_by: string;
  parameters: Record<string, unknown>;
  result: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}

export interface ApiFailure {
  error?: string;
  message?: string;
  details?: Array<{ loc: string[]; msg: string }>;
}
