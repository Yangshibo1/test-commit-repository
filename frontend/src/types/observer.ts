export interface ObserverSessionSummary {
  session_id: string;
  started_at?: string | null;
  ended_at?: string | null;
  cwd?: string | null;
  claude_code_version?: string | null;
  derived: boolean;
  capture_mode?: string | null;
  valid?: boolean | null;
  usable?: boolean | null;
  metrics: ObserverMetrics;
  semantic_available?: boolean;
  semantic_method?: string | null;
  semantic_node_count?: number;
  semantic_valid?: boolean | null;
}

export interface ObserverMetrics {
  human_prompt_count?: number;
  visible_event_count?: number;
  model_response_count?: number;
  tool_call_count?: number;
  tool_error_count?: number;
  incomplete_tool_count?: number;
  local_command_count?: number;
  system_event_count?: number;
  total_cost_usd?: number | null;
  total_duration_ms?: number | null;
  total_api_duration_ms?: number | null;
  total_tool_duration_ms?: number | null;
  total_lines_added?: number | null;
  total_lines_removed?: number | null;
  model_usage?: Record<string, unknown>;
}

export interface ObserverEvent {
  event_id: string;
  sequence: number;
  event_type: string;
  timestamp?: string | null;
  ended_at?: string | null;
  turn_id?: string | null;
  parent_uuid?: string | null;
  message_uuid?: string | null;
  response_id?: string | null;
  tool_use_id?: string | null;
  status: string;
  origin: 'observed' | 'derived' | 'inferred';
  title: string;
  summary: string;
  payload: Record<string, any>;
  evidence: Array<{ source: string; line_number?: number; event_id?: string }>;
  source_lines: number[];
  hidden_by_default: boolean;
}

export interface ObserverTurn {
  turn_id: string;
  prompt_event_id: string;
  prompt: string;
  started_at?: string | null;
  ended_at?: string | null;
  event_ids: string[];
  tool_call_count: number;
  error_count: number;
  status: string;
}

export interface ObserverRelation {
  relation_id: string;
  from: string;
  to: string;
  type: string;
  origin: 'observed' | 'derived' | 'inferred';
}

export interface ObserverTrace {
  schema_version: string;
  session: {
    session_id: string;
    source: string;
    started_at?: string | null;
    ended_at?: string | null;
    cwd?: string | null;
    claude_code_version?: string | null;
    mode?: string | null;
    permission_mode?: string | null;
    primary_model?: string | null;
    transcript_record_count: number;
    parsed_record_count: number;
  };
  turns: ObserverTurn[];
  events: ObserverEvent[];
  relations: ObserverRelation[];
  artifacts: unknown[];
  metrics: ObserverMetrics;
  diagnostics: {
    usable: boolean;
    invalid_transcript_lines: number;
    filtered_non_human_user_records: number;
    incomplete_tool_calls: string[];
    orphan_tool_results: string[];
    duplicate_tool_use_ids: string[];
    broken_parent_uuids: string[];
    record_type_counts: Record<string, number>;
    notes: string[];
  };
}
