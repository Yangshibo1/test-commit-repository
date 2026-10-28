import type { SemanticMetrics } from './semantic';

export type EventBehaviorRole = 'key_decision' | 'normal_execution' | 'key_turning_point' | 'key_result';
// Legacy levels remain readable; do not reinterpret them as new behavior roles.
export type EventImportanceLevel = EventBehaviorRole | 'core' | 'supporting' | 'background';
export interface EventEvidenceRef { event_id: string; field: string; quote: string }
export interface EventBehavior {
  event_id: string; title: string; behavior_summary: string;
  objects: string[]; inputs: string[]; outputs: string[];
  fact_basis: 'requested' | 'planned' | 'performed' | 'reported' | 'unknown';
  evidence_refs: EventEvidenceRef[]; uncertainty: string[]; confidence: string;
}
export interface EventImportance {
  event_id: string; level: EventImportanceLevel; reason: string;
  related_event_ids: string[]; confidence: string;
  neighbor_counts: { rules: number; logical: number };
}
export interface EventLogicalRelation {
  relation_id: string; from: string; to: string; type: string;
  label: string; explanation: string; confidence: string;
  origin: 'inferred'; evidence_check: string; evidence_refs: EventEvidenceRef[];
  catalog_version?: string; connection_basis?: string; limitations?: string[];
  review_status?: 'accepted' | 'candidate' | 'rejected';
  condition_check?: 'met' | 'unmet' | 'uncertain';
  exclusion_check?: 'clear' | 'triggered' | 'uncertain';
  reason?: string; deterministic_issues?: string[];
  context_evidence_refs?: EventEvidenceRef[];
}
export interface EventWorkflow {
  schema_version: 'event-workflow/0.1' | 'event-workflow/0.2' | 'event-workflow/0.3'; session_id: string;
  scope?: {type: 'completed_turns'; cross_turn_inference: false; turns: Array<{turn_id:string; revision:number}>};
  catalog_version?: string;
  source_hashes: { events: string; trace: string };
  event_summaries: EventBehavior[]; logical_relations: EventLogicalRelation[];
  relation_assessments?: EventLogicalRelation[];
  event_importance: EventImportance[];
  inference_run: SemanticMetrics & { inference_id: string; reasoning_effort: string; generated_at: string };
  validation: { valid: boolean; event_count: number; relation_count: number; note: string; candidate_relation_count?: number; rejected_relation_count?: number };
}
export interface EventWorkflowProgress extends SemanticMetrics {
  status: 'idle' | 'scheduled' | 'running' | 'partial' | 'ready';
  stage: string; percent: number; message: string; error?: string | null;
  completed_events?: number; event_count?: number; reasoning_effort?: string;
}
