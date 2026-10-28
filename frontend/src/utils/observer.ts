import type { ObserverEvent, ObserverTrace } from '../types/observer';

const eventClasses: Record<string, ObserverEvent['event_class']> = {
  user_prompt: 'interaction', model_response: 'interaction', assistant_message: 'interaction',
  tool_execution: 'execution', command_execution: 'execution', subagent_result: 'delegation', control_event: 'control',
};

/** Restore display aliases for API responses and offline compact Trace imports. */
export function normalizeObserverTrace(trace: ObserverTrace): ObserverTrace {
  return {
    ...trace,
    events: trace.events.map((event) => {
      const scope = event.scope;
      const sourceLines = event.source_lines ?? event.provenance?.source_lines ?? [];
      const payload = { ...event.payload };
      if (event.event_type === 'command_execution') payload.command ??= payload.input?.command;
      if (event.event_type === 'model_response') {
        payload.response_kind ??= event.event_subtype;
        payload.is_final ??= payload.stop_reason === 'end_turn';
      }
      if (event.event_type === 'subagent_result') {
        payload.task_id ??= scope?.task_id;
        payload.status ??= event.status;
      }
      return {
        ...event, payload,
        event_class: event.event_class ?? eventClasses[event.event_type],
        timestamp: event.timestamp ?? event.time?.started_at,
        ended_at: event.ended_at ?? event.time?.ended_at,
        turn_id: event.turn_id ?? scope?.turn_id,
        response_id: event.response_id ?? scope?.response_id,
        tool_use_id: event.tool_use_id ?? scope?.tool_use_id,
        source_lines: sourceLines,
        evidence: event.evidence ?? sourceLines.map((line_number) => ({ source: event.provenance?.source || 'transcript', line_number })),
        hidden_by_default: event.hidden_by_default ?? false,
      };
    }),
  };
}
