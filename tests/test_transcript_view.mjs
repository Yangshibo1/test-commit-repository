import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTranscriptCards, buildTranscriptTools, formatTranscript, parseTranscript } from '../frontend/src/utils/transcript.ts';

const jsonl = (records) => records.map((record) => JSON.stringify(record)).join('\n') + '\n';

test('formatting keeps escaped message content, invalid rows, blank rows and CRLF separators', () => {
  const record = { type: 'user', message: { content: 'first\nsecond <system-reminder>' } };
  const original = `${JSON.stringify(record)}\r\n\r\ninvalid json\r\n`;
  assert.equal(formatTranscript(original), `${JSON.stringify(record, null, 2)}\r\n\r\ninvalid json\r\n`);
  assert.equal(JSON.parse(formatTranscript(JSON.stringify(record))).message.content, record.message.content);
});

test('parallel tool results match their IDs even when results arrive out of order', () => {
  const lines = parseTranscript(jsonl([
    { type: 'assistant', message: { content: [
      { type: 'tool_use', id: 'read-1', name: 'Read', input: { file_path: '/data.csv' } },
      { type: 'tool_use', id: 'bash-1', name: 'Bash', input: { command: 'pwd' } },
    ] } },
    { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'bash-1', content: '/project' }] } },
    { type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'read-1', content: 'a,b\n1,2' }] } },
  ]));
  const tools = buildTranscriptTools(lines);
  assert.deepEqual(tools.map(({ id, outputs, resultLines, status }) => ({ id, outputs, resultLines, status })), [
    { id: 'read-1', outputs: ['a,b\n1,2'], resultLines: [3], status: 'success' },
    { id: 'bash-1', outputs: ['/project'], resultLines: [2], status: 'success' },
  ]);
});

test('failed, empty, missing and orphan results stay distinguishable', () => {
  const lines = parseTranscript(jsonl([
    { type: 'assistant', message: { content: ['failed', 'empty', 'pending'].map((id) => ({ type: 'tool_use', id, name: 'Bash', input: {} })) } },
    { type: 'user', message: { content: [
      { type: 'tool_result', tool_use_id: 'failed', content: 'exit 1', is_error: true },
      { type: 'tool_result', tool_use_id: 'empty', content: '' },
      { type: 'tool_result', tool_use_id: 'unknown', content: 'orphan result' },
    ] } },
  ]));
  assert.deepEqual(buildTranscriptTools(lines).map((tool) => [tool.id, tool.status]), [
    ['failed', 'error'], ['empty', 'success'], ['pending', 'incomplete'], ['unknown', 'orphan'],
  ]);
});

test('raw log parsing keeps malformed lines, blank lines and original line numbers', () => {
  const lines = parseTranscript('{"type":"mode"}\r\n\r\ninvalid json\r\n{"type":"user","message":{"content":"hello"}}\r\n');
  assert.deepEqual(lines.map(({ line, raw, valid }) => ({ line, raw, valid })), [
    { line: 1, raw: '{"type":"mode"}', valid: true },
    { line: 2, raw: '', valid: false },
    { line: 3, raw: 'invalid json', valid: false },
    { line: 4, raw: '{"type":"user","message":{"content":"hello"}}', valid: true },
  ]);
  assert.deepEqual(buildTranscriptCards(lines).flatMap((card) => card.lines), [1, 2, 3, 4]);
});

test('chain cards preserve user text alongside tool results and group initialization only', () => {
  const lines = parseTranscript(jsonl([
    { type: 'mode', sessionId: 'session-a' },
    { type: 'permission-mode', sessionId: 'session-a' },
    { type: 'user', message: { content: 'Inspect the file' } },
    { type: 'user', message: { content: [
      { type: 'text', text: 'Keep this note' },
      { type: 'tool_result', tool_use_id: 'a', content: 'done' },
    ] } },
  ]));
  const cards = buildTranscriptCards(lines);
  assert.deepEqual(cards.map((card) => card.lines), [[1, 2], [3], [4]]);
  assert.equal(cards[0].title, '系统初始化');
  assert.match(cards[0].text, /session-a/);
  assert.match(cards[2].text, /Keep this note/);
  assert.match(cards[2].text, /done/);
});
