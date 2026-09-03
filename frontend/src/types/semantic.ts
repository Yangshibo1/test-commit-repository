export interface EvidenceField {
  value: string;
  origin: 'observed' | 'derived' | 'inferred' | 'user_validated';
  evidence_event_ids: string[];
  review_id?: string;
}

export interface SemanticNode {
  node_id: string;
  sequence: number;
  episode_ids: string[];
  event_ids: string[];
  primary_activity: string;
  activity_tags: string[];
  specific_intent: EvidenceField;
  goal: EvidenceField;
  summary: EvidenceField;
  outcome_claims: Array<{
    text: string;
    origin: string;
    evidence_event_ids: string[];
    confidence_level: string;
  }>;
  confidence: {
    level: string;
    model_level?: string;
    validated_level?: string;
    evidence_coverage: number;
    boundary_basis: string[];
    uncertainty_reason: string;
  };
  abstained: boolean;
  origin: string;
  inference_method: string;
  review_status: string;
  actions: Array<{
    event_id: string;
    tool_name: string;
    summary: string;
    status: string;
  }>;
  observed_inputs: Array<Record<string, unknown>>;
  reported_outputs: Array<Record<string, unknown>>;
  verified_artifacts: Array<Record<string, unknown>>;
  errors: Array<{
    event_id: string;
    summary: string;
    recovered: boolean;
  }>;
}

export interface SemanticRelation {
  relation_id: string;
  from_node_id: string;
  to_node_id: string;
  type: string;
  origin: string;
  evidence_event_ids: string[];
  confidence_level: string;
}

export interface SemanticWorkflow {
  schema_version: string;
  source_trace: {
    session_id: string;
    path: string;
    sha256: string;
    schema_version: string;
  };
  inference_run: {
    inference_id: string;
    method: string;
    model?: string | null;
    processor_version: string;
    prompt_version: string;
    generated_at: string;
    candidate_count?: number;
    stage_path?: string;
    warnings: string[];
  };
  boundary_decisions?: Array<{
    left_candidate_id: string;
    right_candidate_id: string;
    model_decision?: string | null;
    effective_decision: string;
    decision_origin: string;
    reason: string;
    override_reason?: string | null;
    evidence_event_ids: string[];
    model_confidence?: string | null;
  }>;
  episodes: Array<{
    episode_id: string;
    sequence: number;
    turn_id: string;
    candidate_episode_ids: string[];
    event_ids: string[];
    boundary_basis: string[];
    candidate_kinds?: string[];
    semantic_anchors?: string[];
    segmentation?: {
      origin: string;
      internal_boundaries: Array<Record<string, unknown>>;
    };
    origin: string;
  }>;
  semantic_nodes: SemanticNode[];
  relations: SemanticRelation[];
  validation: {
    valid: boolean;
    evidence_valid?: boolean;
    granularity_valid?: boolean;
    issue_count: number;
    issues: Array<Record<string, unknown>>;
    evidence_issues?: Array<Record<string, unknown>>;
    granularity_issues?: Array<Record<string, unknown>>;
    episode_count: number;
    node_count: number;
    relation_count: number;
    source_event_count: number;
  };
  review: {
    status: string;
    review_event_count: number;
    applied_review_ids?: string[];
    warnings?: string[];
  };
}

export interface SemanticProgress {
  session_id: string;
  status: 'idle' | 'scheduled' | 'running' | 'retrying' | 'partial' | 'ready' | 'failed';
  stage: string;
  percent: number;
  message: string;
  current?: number | null;
  total?: number | null;
  error?: string | null;
  inference_id?: string | null;
  retryable?: boolean;
  completed_episode_count?: number;
  failed_episode?: number | null;
  last_retry?: {
    attempt?: number;
    max_attempts?: number;
    delay_seconds?: number;
    error_type?: string;
  };
}
