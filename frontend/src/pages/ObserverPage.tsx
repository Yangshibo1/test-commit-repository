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
        setSemanticWorkflow(await semanticResponse.json() as SemanticWorkflow);
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
    rulesOnly: boolean,
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
          rules_only: rulesOnly,
          force: !resumeInference,
          resume_inference: resumeInference || null,
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
          setSemanticWorkflow(await semanticResponse.json() as SemanticWorkflow);
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
            sessionId={trace.session.session_id}
            trace={trace}
            workflow={semanticWorkflow}
            loading={loading}
            progress={semanticProgress}
            onGenerate={generateSemantic}
            onWorkflowChange={setSemanticWorkflow}
            onEvidence={openEvidence}
            onError={setError}
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
          <ObserverInspector trace={trace} event={selectedEvent} />
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
