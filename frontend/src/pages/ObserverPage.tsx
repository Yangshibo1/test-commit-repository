import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, MiniMap, Node } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import {
  ObserverEvent,
  ObserverSessionSummary,
  ObserverTrace,
} from '../types/observer';
import { SemanticProgress, SemanticWorkflow } from '../types/semantic';
import SemanticWorkflowView from '../components/SemanticWorkflowView';

const GRAPH_EVENT_TYPES = new Set([
  'user_prompt',
  'model_response',
  'tool_execution',
  'subagent_result',
  'assistant_message',
]);

type ObserverView = 'semantic' | 'execution' | 'raw';

function ObserverPage() {
  const [sessions, setSessions] = useState<ObserverSessionSummary[]>([]);
  const [trace, setTrace] = useState<ObserverTrace | null>(null);
  const [semanticWorkflow, setSemanticWorkflow] = useState<SemanticWorkflow | null>(null);
  const [semanticProgress, setSemanticProgress] = useState<SemanticProgress | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [showInternal, setShowInternal] = useState(false);
  const [view, setView] = useState<ObserverView>('semantic');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTrace = useCallback(async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/trace`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      const value = await response.json() as ObserverTrace;
      setTrace(value);
      setSelectedSessionId(sessionId);
      setSemanticProgress(null);
      setSelectedEventId(value.turns[0]?.prompt_event_id || value.events[0]?.event_id || null);
      const semanticResponse = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/semantic`);
      if (semanticResponse.ok) {
        setSemanticWorkflow(normalizeSemanticWorkflow(await semanticResponse.json()));
      } else {
        setSemanticWorkflow(null);
      }
      const progressResponse = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/semantic/progress`);
      if (progressResponse.ok) {
        const progress = await progressResponse.json() as SemanticProgress;
        setSemanticProgress(progress.status === 'idle' ? null : progress);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '无法读取 Observation');
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/observations');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json() as { sessions: ObserverSessionSummary[] };
      setSessions(body.sessions || []);
      const first = (body.sessions || []).find((item) => item.derived);
      if (first && !selectedSessionId) await loadTrace(first.session_id);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '无法列出 Observation');
    } finally {
      setLoading(false);
    }
  }, [loadTrace, selectedSessionId]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  const handleUpload = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const value = JSON.parse(await file.text()) as ObserverTrace;
      if (value.schema_version !== 'observer-trace/1.0' || !Array.isArray(value.events)) {
        throw new Error('请选择 derive 生成的 observer_trace.json');
      }
      setTrace(value);
      setSemanticWorkflow(null);
      setSemanticProgress(null);
      setSelectedSessionId(value.session.session_id);
      setSelectedEventId(value.turns[0]?.prompt_event_id || value.events[0]?.event_id || null);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : '文件解析失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const visibleEvents = useMemo(() => (
    (trace?.events || []).filter((event) => view === 'raw' || showInternal || !event.hidden_by_default)
  ), [trace, showInternal, view]);
  const selectedEvent = trace?.events.find((event) => event.event_id === selectedEventId) || null;
  const graph = useMemo(() => buildGraph(trace, selectedEventId), [trace, selectedEventId]);

  const generateSemantic = useCallback(async (
    annotationGuidance: string,
    resumeInference?: string | null,
  ) => {
    if (!selectedSessionId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/observations/${encodeURIComponent(selectedSessionId)}/semantic/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rules_only: false,
          force: !resumeInference,
          resume_inference: resumeInference || null,
          annotation_guidance: annotationGuidance,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      if (body.schema_version) {
        setSemanticWorkflow(body as SemanticWorkflow);
        setSemanticProgress(null);
        return;
      }
      let progress = body as SemanticProgress;
      setSemanticProgress(progress);
      for (let attempt = 0; attempt < 800; attempt += 1) {
        if (progress.status === 'ready') {
          const semanticResponse = await fetch(`/api/observations/${encodeURIComponent(selectedSessionId)}/semantic`);
          if (!semanticResponse.ok) throw new Error(`Semantic result HTTP ${semanticResponse.status}`);
          setSemanticWorkflow(normalizeSemanticWorkflow(await semanticResponse.json()));
          return;
        }
        if (progress.status === 'failed') {
          throw new Error(progress.error || '语义工作流生成失败');
        }
        if (progress.status === 'partial') {
          setError(progress.error || '语义处理已暂停，可从检查点继续');
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 750));
        const progressResponse = await fetch(`/api/observations/${encodeURIComponent(selectedSessionId)}/semantic/progress`);
        if (!progressResponse.ok) throw new Error(`Progress HTTP ${progressResponse.status}`);
        progress = await progressResponse.json() as SemanticProgress;
        setSemanticProgress(progress);
      }
      throw new Error('语义工作流生成超时');
    } catch (generationError) {
      setError(generationError instanceof Error ? generationError.message : '语义工作流生成失败');
    } finally {
      setLoading(false);
    }
  }, [selectedSessionId]);

  const openEvidence = useCallback((eventId: string) => {
    setSelectedEventId(eventId);
    setView('execution');
  }, []);

  return (
    <div className="h-full flex flex-col bg-[#fffaf5]">
      <header className="h-[82px] shrink-0 flex items-center gap-4 px-6 border-b border-line bg-[rgba(255,250,240,0.84)]">
        <div className="min-w-0">
          <h1 className="ot-page-title">Passive Observer</h1>
          <p className="ot-meta text-muted mt-1 truncate">
            {trace
              ? `${trace.session.session_id} · ${trace.session.source} · ${trace.schema_version}`
              : '读取 transcript 的确定性派生轨迹；不介入 Claude，不推断语义 Plan'}
          </p>
        </div>
        <nav className="flex items-center gap-1 p-1 rounded-xl bg-[rgba(234,223,212,0.55)] border border-line">
          {([
            ['semantic', '语义工作流'],
            ['execution', '执行轨迹'],
            ['raw', '原始证据'],
          ] as Array<[ObserverView, string]>).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setView(value)}
              className={`px-3 py-1.5 rounded-lg text-xs ${view === value ? 'bg-white text-accent shadow-sm font-semibold' : 'text-muted'}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={selectedSessionId || ''}
            onChange={(event) => event.target.value && void loadTrace(event.target.value)}
            className="max-w-[220px] px-3 py-2 rounded-xl border border-line bg-white ot-meta font-mono"
          >
            <option value="">选择 Session</option>
            {sessions.filter((session) => session.derived).map((session) => (
              <option key={session.session_id} value={session.session_id}>{session.session_id}</option>
            ))}
          </select>
          {view !== 'semantic' && (
            <label className="flex items-center gap-2 px-3 py-2 rounded-xl border border-line bg-white ot-meta cursor-pointer">
              <input
                type="checkbox"
                checked={showInternal}
                onChange={(event) => setShowInternal(event.target.checked)}
              />
              显示内部事件
            </label>
          )}
          <label className="px-3.5 py-2.5 rounded-full border border-line-strong bg-white ot-meta cursor-pointer hover:border-accent">
            加载 observer_trace.json
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(event) => void handleUpload(event.target.files?.[0])}
            />
          </label>
          <button
            type="button"
            onClick={() => void refreshSessions()}
            className="px-3.5 py-2.5 rounded-full border border-line-strong bg-white ot-meta hover:border-accent"
          >
            刷新
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-4 mt-3 px-4 py-2 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {trace && view === 'semantic' ? (
        <div className="flex-1 min-h-0">
          <SemanticWorkflowView
            trace={trace}
            workflow={semanticWorkflow}
            loading={loading}
            progress={semanticProgress}
            onGenerate={generateSemantic}
            onEvidence={openEvidence}
          />
        </div>
      ) : (
      <main className="flex-1 min-h-0 grid grid-cols-[280px_minmax(620px,1fr)_380px] gap-3.5 p-3.5">
        <aside className="min-h-0 grid grid-rows-[210px_1fr] border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
          <section className="min-h-0 border-b border-line overflow-auto">
            <div className="sticky top-0 px-4 py-3 bg-[rgba(255,255,255,0.94)] border-b border-line ot-section-title z-10">
              Observation Sessions
            </div>
            {sessions.map((session) => (
              <button
                type="button"
                key={session.session_id}
                disabled={!session.derived}
                onClick={() => void loadTrace(session.session_id)}
                className={`w-full text-left px-4 py-3 border-b border-line transition-colors disabled:opacity-45 ${
                  selectedSessionId === session.session_id ? 'bg-orange-50' : 'hover:bg-white'
                }`}
              >
                <div className="font-mono text-[10px] break-all">{session.session_id}</div>
                <div className="ot-meta text-muted mt-1">
                  {session.capture_mode || (session.derived ? 'derived' : '等待 derive')}
                  {' · '}{formatDate(session.started_at)}
                </div>
              </button>
            ))}
            {!sessions.length && !loading && (
              <div className="p-5 text-sm text-muted">尚未发现 Observation。</div>
            )}
          </section>

          <section className="min-h-0 overflow-auto">
            <div className="sticky top-0 px-4 py-3 bg-[rgba(255,255,255,0.94)] border-b border-line ot-section-title z-10">
              执行时间线 · {visibleEvents.length}
            </div>
            {visibleEvents.map((event) => (
              <EventCard
                key={event.event_id}
                event={event}
                selected={event.event_id === selectedEventId}
                onSelect={setSelectedEventId}
              />
            ))}
          </section>
        </aside>

        <section className="min-h-0 grid grid-rows-[112px_1fr] gap-3.5">
          <MetricStrip trace={trace} />
          <div className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
            <div className="h-12 flex items-center justify-between px-4 border-b border-line bg-white/60">
              <span className="ot-section-title">Transcript Execution Graph</span>
              <span className="ot-meta text-muted">橙色：执行顺序 · 紫色：工具调用</span>
            </div>
            {trace ? (
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                fitView
                minZoom={0.35}
                maxZoom={1.8}
                onNodeClick={(_, node) => setSelectedEventId(node.id)}
              >
                <Background color="rgba(217,119,69,0.08)" gap={26} />
                <Controls />
                <MiniMap nodeColor={(node) => String(node.style?.borderColor || '#d97745')} />
              </ReactFlow>
            ) : (
              <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
                {loading ? '正在读取派生轨迹…' : '请选择已 derive 的会话，或加载 observer_trace.json。'}
              </div>
            )}
          </div>
        </section>

        <aside className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
          {view === 'raw' ? (
            <RawEvidenceInspector trace={trace} event={selectedEvent} />
          ) : (
            <ObserverInspector trace={trace} event={selectedEvent} />
          )}
        </aside>
      </main>
      )}
    </div>
  );
}

function EventCard({
  event,
  selected,
  onSelect,
}: {
  event: ObserverEvent;
  selected: boolean;
  onSelect: (eventId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(event.event_id)}
      className={`w-full text-left px-4 py-3 border-b border-line transition-colors ${
        selected ? 'bg-orange-50' : 'hover:bg-white'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-sm">{event.title}</span>
        <StatusPill status={event.status} />
      </div>
      <div className="ot-meta text-muted mt-1 line-clamp-2">{event.summary || '无摘要'}</div>
      <div className="ot-meta font-mono text-muted mt-2">
        #{event.sequence} · line {event.source_lines.join(', ')} · {event.origin}
      </div>
    </button>
  );
}

function MetricStrip({ trace }: { trace: ObserverTrace | null }) {
  const metrics = trace?.metrics;
  const values = [
    ['Turns', metrics?.human_prompt_count ?? 0],
    ['Tools', metrics?.tool_call_count ?? 0],
    ['Subagents', metrics?.subagent_result_count ?? 0],
    ['Errors', metrics?.tool_error_count ?? 0],
    ['Tool time', formatDuration(metrics?.total_tool_duration_ms)],
    ['Cost', formatCost(metrics?.total_cost_usd)],
  ];
  return (
    <div className="grid grid-cols-6 gap-2.5 p-3.5 border border-line rounded-3xl bg-white/70">
      {values.map(([label, value]) => (
        <div key={String(label)} className="rounded-2xl border border-line p-3 bg-white/80">
          <div className="ot-stat text-[24px]">{value}</div>
          <div className="ot-meta text-muted mt-1">{label}</div>
        </div>
      ))}
    </div>
  );
}

function ObserverInspector({
  trace,
  event,
}: {
  trace: ObserverTrace | null;
  event: ObserverEvent | null;
}) {
  if (!trace) {
    return <div className="h-full flex items-center justify-center p-8 text-sm text-muted">等待轨迹</div>;
  }
  if (!event) {
    return (
      <div className="h-full overflow-auto p-5">
        <h2 className="font-serif text-2xl">Session</h2>
        <KeyValue label="Session ID" value={trace.session.session_id} />
        <KeyValue label="项目目录" value={trace.session.cwd || '—'} />
        <KeyValue label="Claude Code" value={trace.session.claude_code_version || '—'} />
        <KeyValue label="模型" value={trace.session.primary_model || '—'} />
        <KeyValue label="权限模式" value={trace.session.permission_mode || '—'} />
      </div>
    );
  }
  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-line bg-white/60">
        <div className="ot-meta font-mono text-accent uppercase">{event.event_type}</div>
        <h2 className="font-serif text-2xl mt-1">{event.title}</h2>
        <p className="text-sm text-muted mt-2 break-words">{event.summary}</p>
      </div>
      <div className="flex-1 overflow-auto p-5 space-y-5">
        <section>
          <h3 className="ot-section-title mb-2">可观察属性</h3>
          <KeyValue label="状态" value={event.status} />
          <KeyValue label="来源类型" value={event.origin} />
          <KeyValue label="时间" value={formatDate(event.timestamp)} />
          <KeyValue label="结束时间" value={formatDate(event.ended_at)} />
          <KeyValue label="Turn" value={event.turn_id || '—'} />
          <KeyValue label="Response ID" value={event.response_id || '—'} />
          <KeyValue label="Tool Use ID" value={event.tool_use_id || '—'} />
        </section>
        <section>
          <h3 className="ot-section-title mb-2">Transcript 证据</h3>
          <div className="rounded-xl border border-line bg-white p-3 font-mono text-xs">
            {event.evidence.map((item) => (
              <div key={`${item.source}-${item.line_number || item.event_id}`}>
                {item.source} · line {item.line_number ?? item.event_id}
              </div>
            ))}
          </div>
        </section>
        <section>
          <h3 className="ot-section-title mb-2">Payload</h3>
          <pre className="rounded-xl border border-line bg-[#201d1a] text-[#f8eee5] p-3 text-[11px] leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[440px]">
            {formatPayload(event.payload)}
          </pre>
        </section>
      </div>
    </div>
  );
}

function RawEvidenceInspector({
  trace,
  event,
}: {
  trace: ObserverTrace | null;
  event: ObserverEvent | null;
}) {
  if (!trace) {
    return <div className="h-full flex items-center justify-center p-8 text-sm text-muted">等待轨迹</div>;
  }
  if (!event) {
    return (
      <div className="h-full overflow-auto p-5">
        <h2 className="font-serif text-2xl">原始证据</h2>
        <p className="text-sm text-muted mt-2">选择一个 Event，查看其真实请求、执行结果及 Transcript 证据。</p>
      </div>
    );
  }

  const linkedTools = resolveToolExecutions(trace, event);
  const isToolEnvelope = event.event_type === 'model_response' && linkedTools.length > 0;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-line bg-white/60">
        <div className="ot-meta font-mono text-accent uppercase">{event.event_type}</div>
        <h2 className="font-serif text-2xl mt-1">
          {isToolEnvelope ? `模型发起 ${linkedTools.length} 个工具请求` : event.title}
        </h2>
        <p className="text-sm text-muted mt-2 break-words">
          {isToolEnvelope
            ? linkedTools.map((tool) => toolOperationTitle(tool)).join('；')
            : event.summary}
        </p>
      </div>

      <div className="flex-1 overflow-auto p-5 space-y-5">
        {event.event_type === 'model_response' && (
          <ModelResponseOverview event={event} toolCount={linkedTools.length} />
        )}

        {linkedTools.length > 0 && (
          <section>
            <h3 className="ot-section-title mb-2">
              {event.event_type === 'tool_execution' ? '真实工具请求与结果' : `关联工具调用 · ${linkedTools.length}`}
            </h3>
            <div className="space-y-3">
              {linkedTools.map((tool, index) => (
                <ToolExecutionDetails key={tool.event_id} event={tool} index={index} />
              ))}
            </div>
          </section>
        )}

        {!linkedTools.length && event.event_type === 'model_response' && (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            该模型响应记录了工具调用意图，但当前 Trace 中没有找到对应的 tool_execution Event。
          </section>
        )}

        {event.event_type === 'subagent_result' && <SubagentResultDetails event={event} />}

        {event.event_type !== 'model_response'
          && event.event_type !== 'tool_execution'
          && event.event_type !== 'subagent_result'
          && <ReadableEventDetails event={event} />}

        <details className="rounded-xl border border-line bg-white p-3">
          <summary className="ot-section-title cursor-pointer">技术审计属性</summary>
          <div className="mt-3">
            <KeyValue label="状态" value={event.status} />
            <KeyValue label="来源类型" value={event.origin} />
            <KeyValue label="时间" value={formatDate(event.timestamp)} />
            <KeyValue label="结束时间" value={formatDate(event.ended_at)} />
            <KeyValue label="Event ID" value={event.event_id} />
            <KeyValue label="Turn" value={event.turn_id || '—'} />
            <KeyValue label="Response ID" value={event.response_id || '—'} />
            <KeyValue label="Tool Use ID" value={event.tool_use_id || '—'} />
            <KeyValue label="Message UUID" value={event.message_uuid || '—'} />
            <KeyValue label="Parent UUID" value={event.parent_uuid || '—'} />
          </div>
        </details>

        <details className="rounded-xl border border-line bg-white p-3" open={!linkedTools.length}>
          <summary className="ot-section-title cursor-pointer">Transcript 证据</summary>
          <div className="mt-3 rounded-xl bg-[#fffaf5] p-3 font-mono text-xs">
            {event.evidence.map((item) => (
              <div key={`${item.source}-${item.line_number || item.event_id}`}>
                {item.source} · line {item.line_number ?? item.event_id}
              </div>
            ))}
          </div>
        </details>

        <details className="rounded-xl border border-line bg-white p-3">
          <summary className="ot-section-title cursor-pointer">原始 Event Payload</summary>
          <pre className="mt-3 rounded-xl bg-[#201d1a] text-[#f8eee5] p-3 text-[11px] leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[440px]">
            {formatPayload(event.payload)}
          </pre>
        </details>
      </div>
    </div>
  );
}

function ModelResponseOverview({ event, toolCount }: { event: ObserverEvent; toolCount: number }) {
  const usage = asRecord(event.payload.usage);
  const visibleText = String(event.payload.text || '').trim();
  return (
    <section>
      <h3 className="ot-section-title mb-2">模型动作概览</h3>
      <div className="rounded-xl border border-line bg-white p-3">
        <KeyValue label="模型" value={String(event.payload.model || '—')} />
        <KeyValue label="推理强度" value={String(event.payload.effort || '—')} />
        <KeyValue label="停止原因" value={humanStopReason(event.payload.stop_reason)} />
        <KeyValue label="工具调用" value={`${toolCount} 个`} />
        <KeyValue label="可见文字" value={visibleText || '无；该响应仅发起工具请求'} />
        <KeyValue label="输入 Token" value={formatNumber(usage.input_tokens)} />
        <KeyValue label="输出 Token" value={formatNumber(usage.output_tokens)} />
      </div>
    </section>
  );
}

function ToolExecutionDetails({ event, index }: { event: ObserverEvent; index: number }) {
  const payload = event.payload || {};
  const input = asRecord(payload.input);
  const toolName = String(payload.name || event.title || 'Unknown Tool');
  const operation = describeToolOperation(toolName, input);
  const requestLines = event.source_lines.length ? [event.source_lines[0]] : [];
  const resultLines = event.source_lines.slice(1);
  return (
    <article className={`rounded-2xl border p-4 ${
      event.status === 'error'
        ? 'border-red-200 bg-red-50/70'
        : event.status === 'incomplete'
        ? 'border-amber-200 bg-amber-50/70'
        : 'border-line bg-white'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="ot-meta font-mono text-accent">TOOL {index + 1} · {toolName}</div>
          <h4 className="font-semibold text-base mt-1">{operation.title}</h4>
          {operation.summary && <p className="text-sm text-muted mt-1">{operation.summary}</p>}
        </div>
        <StatusPill status={event.status} />
      </div>

      <div className="mt-3">
        <KeyValue label="操作类型" value={operation.typeLabel} />
        {operation.fields.map(([label, value]) => (
          <KeyValue key={label} label={label} value={value} />
        ))}
        <KeyValue label="观察耗时" value={formatDuration(numberOrNull(payload.observed_elapsed_ms))} />
        <KeyValue label="请求证据" value={formatLines(requestLines)} />
        <KeyValue label="结果证据" value={formatLines(resultLines)} />
      </div>

      {operation.primaryText && (
        <div className="mt-3">
          <div className="ot-meta font-semibold text-muted mb-1">{operation.primaryTextLabel}</div>
          <pre className="rounded-xl border border-line bg-[#fffaf5] p-3 text-xs leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[280px]">
            {operation.primaryText}
          </pre>
        </div>
      )}

      <div className="mt-3">
        <div className="ot-meta font-semibold text-muted mb-1">工具返回</div>
        <pre className="rounded-xl border border-line bg-[#fffaf5] p-3 text-xs leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[320px]">
          {formatReadableValue(payload.output, 12_000) || '未记录工具返回内容'}
        </pre>
      </div>

      {payload.structured_result !== null && payload.structured_result !== undefined && (
        <details className="mt-3 rounded-xl border border-line bg-white/70 p-3">
          <summary className="ot-meta font-semibold cursor-pointer">结构化结果</summary>
          <pre className="mt-2 text-xs leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[280px]">
            {formatReadableValue(payload.structured_result, 12_000)}
          </pre>
        </details>
      )}

      <details className="mt-3 rounded-xl border border-line bg-white/70 p-3">
        <summary className="ot-meta font-semibold cursor-pointer">完整原始请求参数</summary>
        <pre className="mt-2 text-xs leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[360px]">
          {formatReadableValue(input, 20_000)}
        </pre>
      </details>
    </article>
  );
}

function SubagentResultDetails({ event }: { event: ObserverEvent }) {
  const result = event.payload.result;
  return (
    <section>
      <h3 className="ot-section-title mb-2">Subagent 返回结果</h3>
      <div className="rounded-xl border border-line bg-white p-3">
        <KeyValue label="任务" value={String(event.payload.task_summary || event.title)} />
        <KeyValue label="Agent ID" value={String(event.payload.task_id || '—')} />
        <KeyValue label="状态" value={String(event.payload.status || event.status)} />
        <KeyValue label="输出文件" value={String(event.payload.output_file || '—')} />
        <pre className="mt-3 rounded-xl bg-[#fffaf5] p-3 text-xs leading-5 overflow-auto whitespace-pre-wrap break-words max-h-[520px]">
          {formatReadableValue(result, 30_000) || '未记录 Subagent 结果'}
        </pre>
      </div>
    </section>
  );
}

function ReadableEventDetails({ event }: { event: ObserverEvent }) {
  const content = event.payload.content ?? event.payload.text;
  return (
    <section>
      <h3 className="ot-section-title mb-2">记录内容</h3>
      <div className="rounded-xl border border-line bg-white p-3 text-sm leading-6 whitespace-pre-wrap break-words">
        {formatReadableValue(content, 20_000) || event.summary || '没有可见内容'}
      </div>
    </section>
  );
}

interface ToolOperationDescription {
  title: string;
  typeLabel: string;
  summary: string;
  fields: Array<[string, string]>;
  primaryTextLabel?: string;
  primaryText?: string;
}

function resolveToolExecutions(trace: ObserverTrace, event: ObserverEvent): ObserverEvent[] {
  if (event.event_type === 'tool_execution') return [event];
  if (event.event_type !== 'model_response') return [];

  const invokedEventIds = new Set(
    trace.relations
      .filter((relation) => relation.from === event.event_id && relation.type === 'invokes')
      .map((relation) => relation.to),
  );
  const requestedToolIds = new Set(
    Array.isArray(event.payload.tool_use_ids)
      ? event.payload.tool_use_ids.map((value: unknown) => String(value))
      : [],
  );
  return trace.events
    .filter((candidate) => (
      candidate.event_type === 'tool_execution'
      && (
        invokedEventIds.has(candidate.event_id)
        || Boolean(candidate.tool_use_id && requestedToolIds.has(candidate.tool_use_id))
      )
    ))
    .sort((left, right) => left.sequence - right.sequence);
}

function toolOperationTitle(event: ObserverEvent): string {
  const payload = event.payload || {};
  return describeToolOperation(
    String(payload.name || event.title || 'Unknown Tool'),
    asRecord(payload.input),
  ).title;
}

function describeToolOperation(toolName: string, input: Record<string, unknown>): ToolOperationDescription {
  const lower = toolName.toLowerCase();
  if (lower === 'agent') {
    const description = firstString(input.description, input.task, '未命名子代理任务');
    return {
      title: `启动子代理：${description}`,
      typeLabel: 'Agent 委派',
      summary: '主 Agent 请求启动一个子代理执行独立任务。',
      fields: compactFields([
        ['任务描述', description],
        ['子代理类型', firstString(input.subagent_type, '—')],
        ['请求模型', firstString(input.model, '—')],
        ['隔离方式', firstString(input.isolation, '—')],
      ]),
      primaryTextLabel: '委派 Prompt',
      primaryText: firstString(input.prompt),
    };
  }
  if (lower === 'read') {
    const path = firstString(input.file_path, input.path, '未知文件');
    return {
      title: `读取文件：${fileName(path)}`,
      typeLabel: '文件读取',
      summary: path,
      fields: compactFields([
        ['文件', path],
        ['起始位置', optionalString(input.offset)],
        ['读取范围', optionalString(input.limit)],
        ['页码', optionalString(input.pages)],
      ]),
    };
  }
  if (lower === 'write') {
    const path = firstString(input.file_path, input.path, '未知文件');
    const content = firstString(input.content);
    return {
      title: `写入文件：${fileName(path)}`,
      typeLabel: '文件写入',
      summary: path,
      fields: compactFields([
        ['文件', path],
        ['内容长度', content ? `${content.length.toLocaleString()} 字符` : '—'],
      ]),
      primaryTextLabel: '写入内容预览',
      primaryText: truncateText(content, 8_000),
    };
  }
  if (lower === 'edit' || lower === 'notebookedit') {
    const path = firstString(input.file_path, input.notebook_path, input.path, '未知文件');
    const oldText = firstString(input.old_string);
    const newText = firstString(input.new_string);
    return {
      title: `${lower === 'notebookedit' ? '修改 Notebook' : '修改文件'}：${fileName(path)}`,
      typeLabel: lower === 'notebookedit' ? 'Notebook 修改' : '文件修改',
      summary: path,
      fields: compactFields([
        ['文件', path],
        ['替换全部', optionalString(input.replace_all)],
        ['Cell ID', optionalString(input.cell_id)],
        ['Edit Mode', optionalString(input.edit_mode)],
      ]),
      primaryTextLabel: oldText || newText ? '修改内容' : undefined,
      primaryText: oldText || newText
        ? `原内容：\n${truncateText(oldText, 4_000)}\n\n新内容：\n${truncateText(newText, 4_000)}`
        : undefined,
    };
  }
  if (lower === 'glob') {
    const pattern = firstString(input.pattern, '未提供模式');
    const path = firstString(input.path, '当前工作目录');
    return {
      title: `查找文件：${pattern}`,
      typeLabel: '文件发现',
      summary: `在 ${path} 中匹配 ${pattern}`,
      fields: compactFields([
        ['目录', path],
        ['匹配模式', pattern],
      ]),
    };
  }
  if (lower === 'grep') {
    const pattern = firstString(input.pattern, '未提供关键词');
    const path = firstString(input.path, '当前工作目录');
    return {
      title: `搜索内容：${truncateText(pattern, 80)}`,
      typeLabel: '内容搜索',
      summary: `在 ${path} 中搜索匹配内容。`,
      fields: compactFields([
        ['目录', path],
        ['搜索模式', pattern],
        ['文件过滤', optionalString(input.glob)],
        ['输出模式', optionalString(input.output_mode)],
      ]),
    };
  }
  if (['bash', 'powershell', 'shell', 'terminal'].includes(lower)) {
    const command = firstString(input.command, input.cmd, '未记录命令');
    return {
      title: `执行命令：${commandLabel(command)}`,
      typeLabel: '命令执行',
      summary: firstString(input.description),
      fields: compactFields([
        ['工作目录', firstString(input.workdir, input.cwd, '—')],
        ['超时', optionalString(input.timeout)],
      ]),
      primaryTextLabel: '真实命令',
      primaryText: command,
    };
  }
  if (lower === 'taskcreate') {
    const description = firstString(input.description, input.subject, '未命名任务');
    return {
      title: `创建任务：${description}`,
      typeLabel: '任务编排',
      summary: firstString(input.activeForm),
      fields: compactFields([
        ['任务', description],
      ]),
    };
  }
  if (lower === 'taskupdate') {
    return {
      title: `更新任务：${firstString(input.taskId, input.task_id, '未知任务')}`,
      typeLabel: '任务编排',
      summary: '更新任务状态、依赖或描述。',
      fields: compactFields([
        ['Task ID', firstString(input.taskId, input.task_id, '—')],
        ['状态', optionalString(input.status)],
        ['依赖', formatInlineValue(input.blockedBy ?? input.blocked_by)],
        ['描述', optionalString(input.description)],
      ]),
    };
  }

  const likelyPath = firstString(input.file_path, input.path);
  const command = firstString(input.command, input.cmd);
  return {
    title: firstString(input.description, input.subject, `${toolName} 工具调用`),
    typeLabel: '工具调用',
    summary: '该工具没有专用展示适配器，以下内容来自真实请求参数。',
    fields: compactFields([
      ['工具', toolName],
      ['目标路径', likelyPath],
    ]),
    primaryTextLabel: command ? '真实命令' : undefined,
    primaryText: command || undefined,
  };
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, any>
    : {};
}

function compactFields(fields: Array<[string, string]>): Array<[string, string]> {
  return fields.filter(([, value]) => Boolean(value && value !== '—'));
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  }
  return '';
}

function optionalString(value: unknown): string {
  return value === null || value === undefined || value === '' ? '' : String(value);
}

function formatInlineValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function fileName(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

function commandLabel(command: string): string {
  const compact = command.replace(/\s+/g, ' ').trim();
  return truncateText(compact, 90);
}

function truncateText(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, limit)}…`;
}

function formatReadableValue(value: unknown, limit: number): string {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return truncateText(text, limit);
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatLines(lines: number[]): string {
  return lines.length ? `Transcript line ${lines.join(', ')}` : '未单独记录';
}

function formatNumber(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString()
    : '—';
}

function humanStopReason(value: unknown): string {
  const reason = String(value || '');
  if (reason === 'tool_use') return '调用工具';
  if (reason === 'end_turn') return '结束当前回答';
  return reason || '—';
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[90px_1fr] gap-3 py-2 border-b border-line text-xs">
      <span className="text-muted">{label}</span>
      <span className="font-mono break-all">{value}</span>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const style = status === 'error'
    ? 'text-red-700 bg-red-50 border-red-200'
    : status === 'incomplete'
    ? 'text-amber-700 bg-amber-50 border-amber-200'
    : 'text-green-700 bg-green-50 border-green-200';
  return <span className={`px-2 py-0.5 rounded-full border text-[9px] font-mono ${style}`}>{status}</span>;
}

function buildGraph(
  trace: ObserverTrace | null,
  selectedEventId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  if (!trace) return { nodes: [], edges: [] };
  const events = trace.events.filter((event) => (
    GRAPH_EVENT_TYPES.has(event.event_type) && !event.hidden_by_default
  ));
  const eventIds = new Set(events.map((event) => event.event_id));
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: 'TB', ranksep: 72, nodesep: 46, marginx: 30, marginy: 30 });
  graph.setDefaultEdgeLabel(() => ({}));
  events.forEach((event) => graph.setNode(event.event_id, { width: 240, height: 104 }));
  trace.relations
    .filter((relation) => (
      eventIds.has(relation.from)
      && eventIds.has(relation.to)
      && ['next', 'invokes'].includes(relation.type)
    ))
    .forEach((relation) => graph.setEdge(relation.from, relation.to));
  dagre.layout(graph);

  const nodes: Node[] = events.map<Node>((event) => {
    const position = graph.node(event.event_id) || { x: 0, y: 0 };
    const colors = nodeColors(event);
    return {
      id: event.event_id,
      position: { x: position.x - 120, y: position.y - 52 },
      data: { label: `${event.title}\n${event.summary || ''}` },
      style: {
        width: 240,
        minHeight: 104,
        whiteSpace: 'pre-wrap',
        textAlign: 'left',
        fontSize: 12,
        lineHeight: 1.45,
        borderRadius: 16,
        borderWidth: selectedEventId === event.event_id ? 3 : 2,
        borderColor: colors.border,
        background: colors.background,
        color: '#2b2520',
        boxShadow: selectedEventId === event.event_id
          ? '0 12px 28px rgba(217,119,69,0.2)'
          : '0 8px 20px rgba(76,55,32,0.08)',
      },
    };
  });
  const edges: Edge[] = trace.relations
    .filter((relation) => (
      eventIds.has(relation.from)
      && eventIds.has(relation.to)
      && ['next', 'invokes'].includes(relation.type)
    ))
    .map((relation) => ({
      id: relation.relation_id,
      source: relation.from,
      target: relation.to,
      label: relation.type,
      type: 'smoothstep',
      animated: false,
      style: { stroke: relation.type === 'invokes' ? '#8b5cf6' : '#d97745', strokeWidth: 1.8 },
      labelStyle: { fontSize: 9, fill: '#78695c' },
    }));
  return { nodes, edges };
}

function nodeColors(event: ObserverEvent): { border: string; background: string } {
  if (event.status === 'error') return { border: '#dc2626', background: '#fff1f2' };
  if (event.event_type === 'user_prompt') return { border: '#0f766e', background: '#f0fdfa' };
  if (event.event_type === 'model_response') return { border: '#2563eb', background: '#eff6ff' };
  if (event.event_type === 'tool_execution') return { border: '#8b5cf6', background: '#f5f3ff' };
  if (event.event_type === 'subagent_result') return { border: '#0891b2', background: '#ecfeff' };
  return { border: '#d97745', background: '#fff7ed' };
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN');
}

function formatDuration(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(2)}s`;
}

function formatCost(value?: number | null): string {
  return value === null || value === undefined ? '—' : `$${value.toFixed(3)}`;
}

function formatPayload(payload: Record<string, any>): string {
  const value = JSON.stringify(payload, null, 2);
  const limit = 50_000;
  return value.length <= limit
    ? value
    : `${value.slice(0, limit)}\n\n… UI preview truncated; complete value remains in observer_trace.json.`;
}

export default ObserverPage;

function normalizeSemanticWorkflow(value: unknown): SemanticWorkflow {
  const workflow = value as SemanticWorkflow & {
    semantic_nodes?: Array<SemanticWorkflow['semantic_nodes'][number] & {
      specific_intent?: { value?: string; origin?: string; evidence_event_ids?: string[] };
      goal?: { value?: string; origin?: string; evidence_event_ids?: string[] };
    }>;
  };
  workflow.semantic_nodes = (workflow.semantic_nodes || []).map((node) => {
    const legacyNode = node as typeof node & {
      specific_intent?: { value?: string; origin?: string; evidence_event_ids?: string[] };
      goal?: { value?: string; origin?: string; evidence_event_ids?: string[] };
    };
    const legacyIntent = legacyNode.specific_intent;
    const legacyGoal = legacyNode.goal;
    const objective = node.objective || legacyIntent || legacyGoal || {
      value: '未提取阶段目标',
      origin: 'inferred',
      evidence_event_ids: node.event_ids || [],
    };
    const titleSource = String(
      node.title || objective.value || node.primary_activity || '语义阶段',
    ).replace(/[。！？].*$/, '');
    return {
      ...node,
      title: String(node.title || titleSource).slice(0, 36),
      objective,
    };
  });
  return workflow;
}
