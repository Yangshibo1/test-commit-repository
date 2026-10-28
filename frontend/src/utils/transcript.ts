export interface TranscriptLine {
  line: number;
  raw: string;
  type: string;
  timestamp: string;
  record: Record<string, unknown> | null;
  valid: boolean;
}

export interface TranscriptCard {
  id: string;
  sequence: number;
  lines: number[];
  title: string;
  kind: 'system' | 'user' | 'assistant' | 'tool' | 'result' | 'context';
  text: string;
  timestamp: string;
}

export interface TranscriptTool {
  id: string;
  name: string;
  input: unknown;
  outputs: unknown[];
  requestLines: number[];
  resultLines: number[];
  status: 'success' | 'error' | 'incomplete' | 'orphan';
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function parseTranscript(text: string): TranscriptLine[] {
  const lines = text.split(/\r?\n/);
  if (lines[lines.length - 1] === '') lines.pop();
  return lines.map((raw, index) => {
    try {
      const parsed: unknown = JSON.parse(raw);
      const record = asRecord(parsed);
      return { line: index + 1, raw, record, type: String(record.type || 'record'), timestamp: String(record.timestamp || ''), valid: true };
    } catch {
      return { line: index + 1, raw, record: null, type: '无法解析', timestamp: '', valid: false };
    }
  });
}

export function formatTranscript(text: string): string {
  // Formatting is only a display mode. Keep invalid lines and line endings intact.
  return text.split(/(\r?\n)/).map((part, index) => {
    if (index % 2 || !part.trim()) return part;
    try {
      return JSON.stringify(JSON.parse(part), null, 2);
    } catch {
      return part;
    }
  }).join('');
}

function messageContent(line: TranscriptLine): unknown {
  const message = asRecord(line.record?.message);
  return message.content ?? line.record?.content;
}

export function contentBlocks(line: TranscriptLine): Record<string, unknown>[] {
  const content = messageContent(line);
  return Array.isArray(content) ? content.map(asRecord) : [];
}

export function readableContent(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((part) => readableContent(part)).filter(Boolean).join('\n\n');
  const block = asRecord(value);
  if (typeof block.text === 'string') return block.text;
  if (typeof block.content === 'string' || Array.isArray(block.content)) return readableContent(block.content);
  if (block.type === 'image') return '[图片内容，完整数据见原始日志]';
  return value == null ? '' : JSON.stringify(value, null, 2);
}

export function buildTranscriptTools(lines: TranscriptLine[]): TranscriptTool[] {
  const tools = new Map<string, TranscriptTool>();
  for (const line of lines) {
    contentBlocks(line).forEach((block, index) => {
      if (block.type !== 'tool_use' && block.type !== 'tool_result') return;
      const id = String(block.type === 'tool_use' ? block.id || `request-${line.line}-${index}` : block.tool_use_id || `result-${line.line}-${index}`);
      const tool: TranscriptTool = tools.get(id) || { id, name: '未匹配调用', input: null, outputs: [], requestLines: [], resultLines: [], status: 'orphan' };
      if (block.type === 'tool_use') {
        tool.name = String(block.name || 'Tool');
        tool.input = block.input ?? {};
        if (!tool.requestLines.includes(line.line)) tool.requestLines.push(line.line);
      } else {
        tool.outputs.push(block.content ?? '');
        if (!tool.resultLines.includes(line.line)) tool.resultLines.push(line.line);
        if (block.is_error) tool.status = 'error';
      }
      tools.set(id, tool);
    });
  }
  return Array.from(tools.values()).map((tool) => ({
    ...tool,
    status: !tool.requestLines.length ? 'orphan' : tool.status === 'error' ? 'error' : tool.resultLines.length ? 'success' : 'incomplete',
  }));
}

export function buildTranscriptCards(lines: TranscriptLine[]): TranscriptCard[] {
  const cards: TranscriptCard[] = [];
  const firstMessage = lines.findIndex((line) => line.type === 'user' || line.type === 'assistant');
  const initialCount = firstMessage < 0 ? lines.length : firstMessage;
  const initialLines = lines.slice(0, initialCount);
  // Keep malformed/blank lines individually visible, including before the first message.
  const canGroup = initialLines.length > 0 && initialLines.every((line) => line.valid);
  if (canGroup) {
    const sessionId = initialLines.map((line) => line.record?.sessionId || line.record?.session_id).find(Boolean);
    cards.push({ id: 'initialization', sequence: 1, lines: initialLines.map((line) => line.line), title: '系统初始化', kind: 'system', text: `session_id: ${sessionId || '未记录'}\n${initialLines.length} 条初始化记录`, timestamp: initialLines[0].timestamp });
  }
  for (const line of lines.slice(canGroup ? initialCount : 0)) {
    const record = line.record || {};
    const blocks = contentBlocks(line);
    const toolUse = blocks.filter((block) => block.type === 'tool_use');
    const results = blocks.filter((block) => block.type === 'tool_result');
    const texts = blocks.filter((block) => block.type === 'text');
    const content = messageContent(line);
    let kind: TranscriptCard['kind'] = 'context';
    let title = line.valid ? `记录 · ${line.type}` : '无法解析的原始行';
    let text = line.valid && Object.keys(record).length ? JSON.stringify(record, null, 2) : line.raw || '（空行）';
    if (line.type === 'user' || line.type === 'assistant') {
      kind = line.type;
      title = line.type === 'user' ? '用户消息' : '模型响应';
      text = typeof content === 'string' ? content : readableContent(texts);
      if (toolUse.length) {
        kind = 'tool';
        title = `工具调用 · ${toolUse.map((block) => String(block.name || 'Tool')).join('、')}`;
        text = [text, ...toolUse.map((block) => `${block.name || 'Tool'}\n${JSON.stringify(block.input ?? {}, null, 2)}`)].filter(Boolean).join('\n\n');
      } else if (results.length) {
        kind = 'result';
        title = results.some((block) => block.is_error) ? '工具结果 · 执行失败' : '工具结果';
        text = [text, ...results.map((block) => `tool_use_id: ${block.tool_use_id || '未记录'}\n${readableContent(block.content) || '（空结果）'}`)].filter(Boolean).join('\n\n');
      }
      if (!text) text = '无可见文字，完整内容见原始日志。';
    } else if (line.type === 'system') {
      kind = 'system';
      title = `系统事件${record.subtype ? ` · ${record.subtype}` : ''}`;
      text = typeof record.content === 'string' ? record.content : text;
    } else if (line.type === 'attachment') {
      const attachment = asRecord(record.attachment);
      title = `上下文附件${attachment.type ? ` · ${attachment.type}` : ''}`;
      text = readableContent(attachment.content ?? attachment.text ?? attachment);
    }
    cards.push({ id: `record-${line.line}`, sequence: cards.length + 1, lines: [line.line], title, kind, text, timestamp: line.timestamp });
  }
  return cards;
}
