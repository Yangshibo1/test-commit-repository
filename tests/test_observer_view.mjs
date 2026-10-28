import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeObserverTrace } from '../frontend/src/utils/observer.ts';

test('offline compact Trace keeps graph relationships and original-record navigation', () => {
  const event = {
    event_id: 'event-1', event_type: 'command_execution', status: 'success',
    scope: { turn_id: 'turn-1', response_id: 'response-1', tool_use_id: 'tool-1' },
    time: { started_at: 'start', ended_at: 'end' },
    provenance: { source: 'transcript', source_lines: [2, 3] },
    payload: { input: { command: 'python analyze.py' }, output: '2 rows' },
  };
  const trace = { schema_version: 'observer-trace/2.0', events: [event], relations: [{ from: 'response-event', to: 'event-1', type: 'invokes' }] };
  const before = JSON.stringify(trace);
  const restored = normalizeObserverTrace(trace);
  assert.deepEqual(restored.events[0].source_lines, [2, 3]);
  assert.equal(restored.events[0].turn_id, 'turn-1');
  assert.equal(restored.events[0].tool_use_id, 'tool-1');
  assert.equal(restored.events[0].payload.command, 'python analyze.py');
  assert.equal(restored.events[0].payload.output, '2 rows');
  assert.equal(restored.events[0].timestamp, 'start');
  assert.deepEqual(restored.relations, trace.relations);
  assert.equal(JSON.stringify(trace), before);
});

test('legacy display fields, final responses, and subtask correlation remain readable', () => {
  const trace = { events: [
    { event_id: 'legacy', event_type: 'user_prompt', source_lines: [1], timestamp: 'original', payload: { content: 'Task' } },
    { event_id: 'response', event_type: 'model_response', event_subtype: 'text', payload: { stop_reason: 'end_turn', text: 'Done' } },
    { event_id: 'task', event_type: 'subagent_result', status: 'completed', scope: { task_id: 'task-1' }, payload: { result: 'Report' } },
  ] };
  const restored = normalizeObserverTrace(trace);
  assert.deepEqual(restored.events[0].source_lines, [1]);
  assert.equal(restored.events[0].timestamp, 'original');
  assert.equal(restored.events[1].payload.is_final, true);
  assert.equal(restored.events[2].payload.task_id, 'task-1');
  assert.equal(restored.events[2].payload.result, 'Report');
});
