import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MarkerType,
  MiniMap,
  Node,
  NodeProps,
  Position,
  ReactFlowInstance,
  useViewport,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import {
  ObserverEvent,
  ObserverRelation,
  ObserverSessionSummary,
  ObserverTrace,
} from '../types/observer';
import { SemanticProgress, SemanticWorkflow } from '../types/semantic';
import SemanticWorkflowView from '../components/SemanticWorkflowView';

const GRAPH_EVENT_TYPES = new Set([
  'user_prompt',
  'model_response',
  'tool_execution',
  'command_execution',
  'subagent_result',
  'control_event',
  // Legacy observer-trace/1.0 compatibility.
  'assistant_message',
]);

const EXECUTION_LOGICAL_RELATIONS = new Set([
  'prompts',
  'invokes',
  'result_feeds',
  'spawns',
  'depends_on',
]);
const EXECUTION_READING_ZOOM = 0.82;
const EXECUTION_NODE_WIDTH = 276;
const EXECUTION_NODE_HEIGHT = 124;
const ARTIFACT_NODE_WIDTH = 228;
const ARTIFACT_NODE_HEIGHT = 72;

interface ExecutionGraphNodeData {
  nodeKind: 'execution';
  sequence: number;
  typeLabel: string;
  title: string;
  summary: string;
  status: string;
  accent: string;
}

interface ArtifactGraphNodeData {
  nodeKind: 'artifact';
  name: string;
  path: string;
  exists: boolean;
  accent: string;
  onOpen: () => void;
}

const ExecutionGraphNode = memo(({ data, selected }: NodeProps<ExecutionGraphNodeData>) => {
  const { zoom } = useViewport();
  const overview = zoom < 0.6;
  const compact = zoom >= 0.6 && zoom < 0.8;
  const status = executionStatusDisplay(data.status);

  return (
    <div
      className={`relative h-full w-full overflow-hidden rounded-2xl border bg-[#fffdfb] font-sans transition-[box-shadow,border-color] duration-200 ${
        selected
          ? 'border-accent shadow-[0_16px_34px_rgba(217,119,69,0.24)]'
          : 'border-[#e7ded3] shadow-[0_8px_22px_rgba(76,55,32,0.10)]'
      }`}
      style={{ borderLeftWidth: 4, borderLeftColor: data.accent }}
      title={`${String(data.sequence).padStart(2, '0')} · ${data.typeLabel} · ${data.title}`}
    >
      {overview ? (
        <div className="flex h-full items-center gap-4 px-5">
          <span className="text-3xl font-semibold tabular-nums" style={{ color: data.accent }}>
            {String(data.sequence).padStart(2, '0')}
          </span>
          <div className="min-w-0">
            <div className="truncate text-base font-semibold text-[#302a25]">{data.typeLabel}</div>
            <div className="mt-1 h-1.5 w-16 rounded-full" style={{ backgroundColor: data.accent }} />
          </div>
        </div>
      ) : (
        <div className="flex h-full min-w-0 flex-col px-4 py-3">
          <div className="flex shrink-0 items-center gap-2 overflow-hidden">
            <span
              className="inline-flex h-6 min-w-8 shrink-0 items-center justify-center rounded-md px-1.5 text-xs font-bold tabular-nums text-white"
              style={{ backgroundColor: data.accent }}
            >
              {String(data.sequence).padStart(2, '0')}
            </span>
            <span className="min-w-0 truncate rounded-full bg-stone-100 px-2 py-1 text-[11px] font-semibold text-[#625a52]">
              {data.typeLabel}
            </span>
            <span className="ml-auto flex shrink-0 items-center gap-1.5 text-[10px] font-semibold" style={{ color: status.color }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: status.color }} />
              {status.label}
            </span>
          </div>
          <div className="mt-2 line-clamp-2 overflow-hidden break-words text-[15px] font-semibold leading-5 text-[#29241f]">
            {data.title}
          </div>
          {!compact && data.summary && (
            <div className="mt-auto truncate text-[11px] font-medium leading-4 text-[#7a7067]" title={data.summary}>
              {data.summary}
            </div>
          )}
        </div>
      )}

      <Handle type="target" position={Position.Top} id="main-in" className="!h-1.5 !w-1.5 !border-0 !opacity-0" />
      <Handle type="source" position={Position.Bottom} id="main-out" className="!h-1.5 !w-1.5 !border-0 !opacity-0" />
      <Handle type="source" position={Position.Right} id="artifact-out" className="!h-1.5 !w-1.5 !border-0 !opacity-0" />
    </div>
  );
});

ExecutionGraphNode.displayName = 'ExecutionGraphNode';

const ArtifactGraphNode = memo(({ data }: NodeProps<ArtifactGraphNodeData>) => (
  <div
    className="relative flex h-full w-full items-center gap-3 overflow-hidden rounded-xl border border-[#e7ded3] bg-white px-3.5 shadow-[0_6px_16px_rgba(76,55,32,0.08)]"
    style={{ borderLeftWidth: 4, borderLeftColor: data.accent }}
    title={data.path}
  >
    <span
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white"
      style={{ backgroundColor: data.accent }}
      aria-hidden="true"
    >
      F
    </span>
    <div className="min-w-0 flex-1">
      <div className="truncate text-[13px] font-semibold text-[#302a25]">{data.name}</div>
      {data.exists ? (
        <button
          type="button"
          className="nodrag nopan mt-1 text-[11px] font-semibold text-[#b85f32] underline decoration-[#d9a181] underline-offset-2 hover:text-[#8f3f1f]"
          onClick={(event) => {
            event.stopPropagation();
            data.onOpen();
          }}
        >
          打开本地文件 ↗
        </button>
      ) : (
        <span className="mt-1 block text-[11px] font-medium text-[#9b9188]">文件不可用</span>
      )}
    </div>
    <Handle type="target" position={Position.Left} id="artifact-in" className="!h-1.5 !w-1.5 !border-0 !opacity-0" />
  </div>
));

ArtifactGraphNode.displayName = 'ArtifactGraphNode';

const executionNodeTypes = {
  execution: ExecutionGraphNode,
  artifact: ArtifactGraphNode,
};

type ObserverView = 'semantic' | 'execution' | 'raw';

interface ObserverPageProps {
  onNavigate: (page: 'claude' | 'records' | 'observer') => void;
}

function ObserverPage({ onNavigate }: ObserverPageProps) {
  const [sessions, setSessions] = useState<ObserverSessionSummary[]>([]);
  const [trace, setTrace] = useState<ObserverTrace | null>(null);
  const [semanticWorkflow, setSemanticWorkflow] = useState<SemanticWorkflow | null>(null);
  const [semanticProgress, setSemanticProgress] = useState<SemanticProgress | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedPlanGroupId, setSelectedPlanGroupId] = useState<string | null>(null);
  const [executionFlow, setExecutionFlow] = useState<ReactFlowInstance | null>(null);
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
      setSelectedPlanGroupId(null);
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
      if (!['observer-trace/1.0', 'observer-trace/2.0'].includes(value.schema_version) || !Array.isArray(value.events)) {
        throw new Error('请选择 derive 生成的 observer_trace.json');
      }
      setTrace(value);
      setSemanticWorkflow(null);
      setSemanticProgress(null);
      setSelectedSessionId(value.session.session_id);
      setSelectedPlanGroupId(null);
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
  const taskRegistry = useMemo(() => buildTaskRegistry(trace), [trace]);
  const planGroups = useMemo(
    () => buildPlanDisplayGroups(trace, taskRegistry),
    [trace, taskRegistry],
  );
  const selectedPlanGroup = planGroups.find((group) => group.groupId === selectedPlanGroupId) || null;
  const rawTimelineItems = useMemo(
    () => buildRawTimelineItems(visibleEvents, planGroups),
    [visibleEvents, planGroups],
  );
  const selectEvent = useCallback((eventId: string) => {
    setSelectedPlanGroupId(null);
    setSelectedEventId(eventId);
  }, []);

  const openLocalArtifact = useCallback(async (artifactId: string) => {
    if (!selectedSessionId) return;
    setError(null);
    try {
      const response = await fetch(
        `/api/observations/${encodeURIComponent(selectedSessionId)}/artifacts/${encodeURIComponent(artifactId)}/open`,
        { method: 'POST' },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
    } catch (openError) {
      const message = openError instanceof Error ? openError.message : String(openError);
      setError(`无法打开本地文件：${message}`);
    }
  }, [selectedSessionId]);

  const selectGraphNode = useCallback((nodeId: string) => {
    if ((trace?.artifacts || []).some((artifact) => artifact.artifact_id === nodeId)) {
      return;
    }
    if (nodeId.startsWith('plan-group-')) {
      setSelectedEventId(null);
      setSelectedPlanGroupId(nodeId);
      return;
    }
    selectEvent(nodeId);
  }, [selectEvent, trace]);

  const graph = useMemo(
    () => buildGraph(
      trace,
      selectedEventId,
      view === 'raw',
      taskRegistry,
      planGroups,
      selectedPlanGroupId,
      openLocalArtifact,
    ),
    [trace, selectedEventId, view, taskRegistry, planGroups, selectedPlanGroupId, openLocalArtifact],
  );

  useEffect(() => {
    if (!executionFlow || view === 'semantic' || !selectedEventId) return;
    const node = graph.nodes.find((candidate) => candidate.id === selectedEventId);
    if (!node) return;
    const width = Number(node.style?.width) || EXECUTION_NODE_WIDTH;
    const height = Number(node.style?.height || node.style?.minHeight) || EXECUTION_NODE_HEIGHT;
    void executionFlow.setCenter(
      node.position.x + width / 2,
      node.position.y + height / 2,
      { zoom: EXECUTION_READING_ZOOM, duration: 280 },
    );
  }, [executionFlow, graph.nodes, selectedEventId, view]);

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
      <header className="h-16 shrink-0 flex items-center gap-3 px-4 border-b border-line bg-[rgba(255,250,240,0.9)] backdrop-blur-2xl z-20">
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-9 h-9 border border-[rgba(217,119,69,0.42)] rounded-xl flex items-center justify-center bg-gradient-to-br from-white to-[#fff6ef] shadow-md">
            <span className="text-accent font-bold text-xs rotate-[-4deg]">AV</span>
          </div>
          <div>
            <div className="font-serif text-base leading-none">AgentVAST</div>
            <div className="text-[8px] text-muted font-mono mt-1">LOCAL CLAUDE WORKBENCH</div>
          </div>
        </div>
        <nav className="flex items-center gap-0.5 p-1 rounded-xl bg-[rgba(234,223,212,0.55)] border border-line shrink-0">
          {([
            ['claude', 'Claude 对话'],
            ['records', '工作流记录'],
            ['observer', '被动观察'],
          ] as Array<['claude' | 'records' | 'observer', string]>).map(([page, label]) => (
            <button
              key={page}
              type="button"
              onClick={() => onNavigate(page)}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all ${page === 'observer' ? 'bg-white text-accent shadow-sm font-semibold' : 'text-muted hover:text-ink'}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="min-w-0 max-w-[230px] border-l border-line pl-3">
          <div className="font-serif text-sm leading-none">Passive Observer</div>
          <p className="text-[9px] font-mono text-muted mt-1 truncate">
            {trace
              ? `${trace.session.session_id} · ${trace.session.source} · ${trace.schema_version}`
              : '读取 transcript 的确定性派生轨迹；不介入 Claude，不推断语义 Plan'}
          </p>
        </div>
        <nav className="flex items-center gap-0.5 p-1 rounded-xl bg-[rgba(234,223,212,0.55)] border border-line shrink-0">
          {([
            ['semantic', '语义工作流'],
            ['execution', '执行轨迹'],
          ] as Array<[ObserverView, string]>).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setView(value)}
              className={`px-2.5 py-1.5 rounded-lg text-[11px] ${view === value ? 'bg-white text-accent shadow-sm font-semibold' : 'text-muted'}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1.5 min-w-0">
          <select
            value={selectedSessionId || ''}
            onChange={(event) => event.target.value && void loadTrace(event.target.value)}
            className="w-[190px] px-2.5 py-2 rounded-xl border border-line bg-white text-[10px] font-mono"
          >
            <option value="">选择 Session</option>
            {sessions.filter((session) => session.derived).map((session) => (
              <option key={session.session_id} value={session.session_id}>{session.session_id}</option>
            ))}
          </select>
          {view !== 'semantic' && (
            <label className="flex items-center gap-1.5 px-2.5 py-2 rounded-xl border border-line bg-white text-[10px] cursor-pointer whitespace-nowrap">
              <input
                type="checkbox"
                checked={showInternal}
                onChange={(event) => setShowInternal(event.target.checked)}
              />
              显示内部事件
            </label>
          )}
          <label className="px-2.5 py-2 rounded-xl border border-line-strong bg-white text-[10px] cursor-pointer hover:border-accent whitespace-nowrap">
            加载 Trace
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
            className="px-2.5 py-2 rounded-xl border border-line-strong bg-white text-[10px] hover:border-accent"
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
            onOpenArtifact={openLocalArtifact}
          />
        </div>
      ) : (
      <main className="flex-1 min-h-0 grid grid-cols-[240px_minmax(620px,1fr)_320px] gap-2.5 p-2.5">
        <aside className="min-h-0 grid grid-rows-[170px_1fr] border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
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
              {view === 'raw' ? 'Event 证据列表' : '执行时间线'} · {view === 'raw' ? rawTimelineItems.length : visibleEvents.length}
            </div>
            {view === 'raw'
              ? rawTimelineItems.map((item) => (
                  item.kind === 'plan_group' ? (
                    <PlanGroupCard
                      key={item.group.groupId}
                      group={item.group}
                      selected={item.group.groupId === selectedPlanGroupId}
                      onSelect={setSelectedPlanGroupId}
                    />
                  ) : (
                    <EventCard
                      key={item.event.event_id}
                      event={item.event}
                      trace={trace}
                      taskRegistry={taskRegistry}
                      rawMode
                      selected={item.event.event_id === selectedEventId}
                      onSelect={selectEvent}
                    />
                  )
                ))
              : visibleEvents.map((event) => (
                  <EventCard
                    key={event.event_id}
                    event={event}
                    trace={trace}
                    taskRegistry={taskRegistry}
                    rawMode={false}
                    selected={event.event_id === selectedEventId}
                    onSelect={selectEvent}
                  />
                ))}
          </section>
        </aside>

        <section className="min-h-0 grid grid-rows-[88px_1fr] gap-2.5">
          <MetricStrip trace={trace} />
          <div className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
            <div className="h-12 flex items-center justify-between gap-3 px-4 border-b border-line bg-white/60">
              <span className="ot-section-title">
                {view === 'raw' ? 'Event Logic Graph' : 'Transcript Execution Graph'}
              </span>
              <div className="flex items-center gap-2">
                <span className="hidden xl:inline ot-meta text-muted">
                  {view === 'raw'
                    ? '蓝色：模型批次 · 紫色：工具执行 · invokes：批次调用关系'
                    : '橙色：逻辑关系 · 浅橙：时间补位'}
                </span>
                <button
                  type="button"
                  disabled={!selectedEventId}
                  onClick={() => {
                    if (!executionFlow || !selectedEventId) return;
                    const node = graph.nodes.find((candidate) => candidate.id === selectedEventId);
                    if (!node) return;
                    const width = Number(node.style?.width) || 240;
                    const height = Number(node.style?.height || node.style?.minHeight) || 104;
                    void executionFlow.setCenter(
                      node.position.x + width / 2,
                      node.position.y + height / 2,
                      { zoom: EXECUTION_READING_ZOOM, duration: 280 },
                    );
                  }}
                  className="rounded-full border border-line bg-white px-3 py-1 text-[11px] font-semibold text-[#675e56] shadow-sm hover:border-accent disabled:opacity-40"
                >
                  定位当前
                </button>
                <button
                  type="button"
                  onClick={() => void executionFlow?.fitView({ padding: 0.08, minZoom: 0.05, maxZoom: 0.35, duration: 320 })}
                  className="rounded-full border border-line bg-white px-3 py-1 text-[11px] font-semibold text-[#675e56] shadow-sm hover:border-accent"
                >
                  全览
                </button>
              </div>
            </div>
            {trace ? (
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                nodeTypes={executionNodeTypes}
                defaultViewport={{ x: 80, y: 12, zoom: EXECUTION_READING_ZOOM }}
                minZoom={0.05}
                maxZoom={1.4}
                nodesDraggable={false}
                onInit={setExecutionFlow}
                onNodeClick={(_, node) => selectGraphNode(node.id)}
              >
                <Background color="rgba(217,119,69,0.08)" gap={26} />
                <Controls />
                <MiniMap nodeColor={(node) => String(node.data?.accent || node.style?.borderColor || '#d97745')} />
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
            selectedPlanGroup ? (
              <PlanGroupInspector
                group={selectedPlanGroup}
                trace={trace!}
                onSelectEvent={selectEvent}
              />
            ) : (
              <RawEvidenceInspector
                trace={trace}
                event={selectedEvent}
                taskRegistry={taskRegistry}
              />
            )
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
  trace,
  taskRegistry,
  rawMode,
  selected,
  onSelect,
}: {
  event: ObserverEvent;
  trace: ObserverTrace | null;
  taskRegistry: TaskRegistry;
  rawMode: boolean;
  selected: boolean;
  onSelect: (eventId: string) => void;
}) {
  if (!rawMode) {
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

  const display = rawMode && trace
    ? rawEventDisplay(trace, event, taskRegistry)
    : {
        typeLabel: eventTypeLabel(event.event_type),
        title: event.title,
        summary: event.summary || '无摘要',
        context: event.origin,
      };
  return (
    <button
      type="button"
      onClick={() => onSelect(event.event_id)}
      className={`w-full text-left px-4 py-3 border-b border-line transition-colors ${
        selected ? 'bg-orange-50' : 'hover:bg-white'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="ot-meta font-mono text-accent uppercase">{display.typeLabel}</span>
        <StatusPill status={event.status} />
      </div>
      <div className="font-semibold text-sm mt-1 line-clamp-2">{display.title}</div>
      <div className="ot-meta text-muted mt-1 line-clamp-2">{display.summary}</div>
      {rawMode && display.context && (
        <div className="ot-meta text-muted mt-2 line-clamp-1">{display.context}</div>
      )}
      <div className="ot-meta font-mono text-muted mt-2">
        #{event.sequence} · line {event.source_lines.join(', ')}
      </div>
    </button>
  );
}

function PlanGroupCard({
  group,
  selected,
  onSelect,
}: {
  group: PlanDisplayGroup;
  selected: boolean;
  onSelect: (groupId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(group.groupId)}
      className={`w-full text-left px-4 py-4 border-b border-line transition-colors ${
        selected ? 'bg-violet-50' : 'bg-white/50 hover:bg-white'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="ot-meta font-mono text-violet-700 uppercase">展示分组 · 任务规划</span>
        <StatusPill status={group.status} />
      </div>
      <div className="font-semibold text-sm mt-2">{group.title}</div>
      <div className="ot-meta text-muted mt-1">{group.summary}</div>
      <div className="ot-meta text-violet-700 mt-2">
        {group.tasks.length} 项任务 · {group.dependencyCount} 条依赖 · {group.memberEventIds.length} 个原始 Event
      </div>
      <div className="ot-meta font-mono text-muted mt-2">
        #{group.startSequence}–{group.endSequence} · 点击展开计划
      </div>
    </button>
  );
}

function PlanGroupInspector({
  group,
  trace,
  onSelectEvent,
}: {
  group: PlanDisplayGroup;
  trace: ObserverTrace;
  onSelectEvent: (eventId: string) => void;
}) {
  const eventMap = new Map(trace.events.map((event) => [event.event_id, event]));
  const members = group.memberEventIds
    .map((eventId) => eventMap.get(eventId))
    .filter((event): event is ObserverEvent => Boolean(event));
  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-line bg-white/60">
        <div className="ot-meta font-mono text-violet-700 uppercase">DISPLAY GROUP · PLAN DEFINITION</div>
        <h2 className="font-serif text-2xl mt-1">{group.title}</h2>
        <p className="text-sm text-muted mt-2">{group.summary}</p>
      </div>
      <div className="flex-1 overflow-auto p-5 space-y-5">
        <section>
          <h3 className="ot-section-title mb-2">计划结构</h3>
          <div className="space-y-3">
            {group.tasks.map((task) => (
              <div key={task.taskId} className="rounded-xl border border-line bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="ot-meta font-mono text-accent">TASK #{task.taskId}</div>
                    <div className="font-semibold text-sm mt-1">{task.subject}</div>
                  </div>
                  <span className="ot-meta text-muted">{task.dependsOn.length ? `${task.dependsOn.length} dependencies` : 'root task'}</span>
                </div>
                <p className="text-sm text-muted leading-6 mt-2">{task.description || '未记录计划目标'}</p>
                {task.activeForm && <div className="ot-meta mt-2">执行中描述：{task.activeForm}</div>}
                <div className="mt-3">
                  <div className="ot-meta font-semibold text-muted">前置依赖</div>
                  <div className="ot-meta mt-1">
                    {task.dependsOn.length
                      ? task.dependsOn.map((id) => {
                          const dependency = group.tasks.find((candidate) => candidate.taskId === id);
                          return dependency ? `#${id} ${dependency.subject}` : `#${id}`;
                        }).join('、')
                      : '无'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h3 className="ot-section-title mb-2">依赖关系</h3>
          <div className="rounded-xl border border-line bg-white p-3 space-y-2">
            {group.tasks.flatMap((task) => task.dependsOn.map((dependencyId) => {
              const dependency = group.tasks.find((candidate) => candidate.taskId === dependencyId);
              return (
                <div key={`${dependencyId}-${task.taskId}`} className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center text-xs">
                  <span>#{dependencyId} {dependency?.subject || ''}</span>
                  <span className="font-mono text-violet-700">→</span>
                  <span>#{task.taskId} {task.subject}</span>
                </div>
              );
            }))}
            {!group.dependencyCount && <div className="text-sm text-muted">未设置任务依赖。</div>}
          </div>
        </section>

        <details className="rounded-xl border border-line bg-white p-3">
          <summary className="ot-section-title cursor-pointer">原始 Event · {members.length}</summary>
          <div className="mt-3 space-y-2">
            {members.map((event) => (
              <button
                key={event.event_id}
                type="button"
                onClick={() => onSelectEvent(event.event_id)}
                className="w-full text-left rounded-xl border border-line bg-[#fffaf5] px-3 py-2 hover:border-accent"
              >
                <div className="flex justify-between gap-2">
                  <span className="ot-meta font-mono text-accent">#{event.sequence} · {eventTypeLabel(event.event_type)}</span>
                  <span className="ot-meta text-muted">line {event.source_lines.join(', ')}</span>
                </div>
                <div className="text-xs mt-1">{event.title} · {event.summary}</div>
              </button>
            ))}
          </div>
        </details>

        <div className="rounded-xl border border-violet-200 bg-violet-50 p-3 text-xs text-violet-800">
          这是由 {group.memberEventIds.length} 个真实 Event 确定性组织出的前端展示组，不是新的 Event，也没有修改 observer_trace.json。
        </div>
      </div>
    </div>
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
  taskRegistry,
}: {
  trace: ObserverTrace | null;
  event: ObserverEvent | null;
  taskRegistry: TaskRegistry;
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
            ? linkedTools.map((tool) => toolOperationTitle(tool, taskRegistry)).join('；')
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
              {isExecutionEvent(event) ? '真实执行请求与结果' : `关联执行调用 · ${linkedTools.length}`}
            </h3>
            <div className="space-y-3">
              {linkedTools.map((tool, index) => (
                <ToolExecutionDetails
                  key={tool.event_id}
                  event={tool}
                  index={index}
                  taskRegistry={taskRegistry}
                />
              ))}
            </div>
          </section>
        )}

        {!linkedTools.length && event.event_type === 'model_response' && toolUseIds(event).length > 0 && (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            该模型响应记录了执行调用意图，但当前 Trace 中没有找到对应的执行 Event。
          </section>
        )}

        {event.event_type === 'subagent_result' && <SubagentResultDetails event={event} />}

        {event.event_type !== 'model_response'
          && !isExecutionEvent(event)
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

function ToolExecutionDetails({
  event,
  index,
  taskRegistry,
}: {
  event: ObserverEvent;
  index: number;
  taskRegistry: TaskRegistry;
}) {
  const payload = event.payload || {};
  const input = asRecord(payload.input);
  const toolName = String(payload.name || event.title || 'Unknown Tool');
  const operation = describeToolOperation(toolName, input, event.payload.structured_result, taskRegistry);
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

interface EventDisplayDescription {
  typeLabel: string;
  title: string;
  summary: string;
  context: string;
}

interface TaskDefinition {
  taskId: string;
  subject: string;
  description: string;
  activeForm: string;
  createEventId: string;
}

type TaskRegistry = Record<string, TaskDefinition>;

interface PlanTask extends TaskDefinition {
  dependsOn: string[];
}

interface PlanDisplayGroup {
  groupId: string;
  title: string;
  summary: string;
  startSequence: number;
  endSequence: number;
  memberEventIds: string[];
  tasks: PlanTask[];
  dependencyCount: number;
  status: 'complete' | 'error' | 'incomplete';
}

type RawTimelineItem =
  | { kind: 'event'; event: ObserverEvent }
  | { kind: 'plan_group'; group: PlanDisplayGroup };

function buildTaskRegistry(trace: ObserverTrace | null): TaskRegistry {
  if (!trace) return {};
  const registry: TaskRegistry = {};
  trace.events
    .filter((event) => (
      event.event_type === 'tool_execution'
      && String(event.payload.name || '').toLowerCase() === 'taskcreate'
    ))
    .sort((left, right) => left.sequence - right.sequence)
    .forEach((event) => {
      const input = asRecord(event.payload.input);
      const structured = asRecord(event.payload.structured_result);
      const structuredTask = asRecord(structured.task);
      const taskId = firstString(
        structuredTask.id,
        structured.taskId,
        extractTaskId(event.payload.output),
      );
      if (!taskId) return;
      registry[taskId] = {
        taskId,
        subject: firstString(input.subject, structuredTask.subject, `任务 #${taskId}`),
        description: firstString(input.description),
        activeForm: firstString(input.activeForm),
        createEventId: event.event_id,
      };
    });
  return registry;
}

function buildPlanDisplayGroups(
  trace: ObserverTrace | null,
  taskRegistry: TaskRegistry,
): PlanDisplayGroup[] {
  if (!trace) return [];
  const events = [...trace.events].sort((left, right) => left.sequence - right.sequence);
  const planningTools = events.filter(isPlanStructureToolEvent);
  if (!planningTools.length) return [];

  const clusters: ObserverEvent[][] = [];
  let current: ObserverEvent[] = [];
  for (const event of planningTools) {
    const previous = current[current.length - 1];
    if (
      previous
      && (
        previous.turn_id !== event.turn_id
        || hasPlanBoundaryBetween(events, previous.sequence, event.sequence)
      )
    ) {
      clusters.push(current);
      current = [];
    }
    current.push(event);
  }
  if (current.length) clusters.push(current);

  return clusters.map((toolEvents, groupIndex) => {
    const memberEvents: ObserverEvent[] = [];
    for (const toolEvent of toolEvents) {
      memberEvents.push(toolEvent);
      const parentResponses = trace.relations
        .filter((relation) => relation.type === 'invokes' && relation.to === toolEvent.event_id)
        .map((relation) => events.find((event) => event.event_id === relation.from))
        .filter((event): event is ObserverEvent => Boolean(event));
      memberEvents.push(...parentResponses);
    }
    const uniqueMembers = [...new Map(memberEvents.map((event) => [event.event_id, event])).values()]
      .sort((left, right) => left.sequence - right.sequence);
    const taskIds = new Set<string>();
    const dependencies = new Map<string, Set<string>>();
    for (const toolEvent of toolEvents) {
      const input = asRecord(toolEvent.payload.input);
      const toolName = String(toolEvent.payload.name || '').toLowerCase();
      if (toolName === 'taskcreate') {
        const structured = asRecord(toolEvent.payload.structured_result);
        const structuredTask = asRecord(structured.task);
        const taskId = firstString(
          structuredTask.id,
          structured.taskId,
          extractTaskId(toolEvent.payload.output),
        );
        if (taskId) taskIds.add(taskId);
      } else {
        const taskId = firstString(input.taskId, input.task_id);
        if (!taskId) continue;
        taskIds.add(taskId);
        const values = arrayStrings(input.addBlockedBy ?? input.blockedBy ?? input.blocked_by);
        const target = dependencies.get(taskId) || new Set<string>();
        values.forEach((value) => {
          target.add(value);
          taskIds.add(value);
        });
        dependencies.set(taskId, target);
      }
    }
    const tasks = [...taskIds]
      .map((taskId) => ({
        ...(taskRegistry[taskId] || {
          taskId,
          subject: `任务 #${taskId}`,
          description: '',
          activeForm: '',
          createEventId: '',
        }),
        dependsOn: [...(dependencies.get(taskId) || [])],
      }))
      .sort((left, right) => Number(left.taskId) - Number(right.taskId));
    const dependencyCount = tasks.reduce((total, task) => total + task.dependsOn.length, 0);
    const status = toolEvents.some((event) => event.status === 'error')
      ? 'error'
      : toolEvents.some((event) => event.status === 'incomplete')
      ? 'incomplete'
      : 'complete';
    const startSequence = uniqueMembers[0]?.sequence || toolEvents[0].sequence;
    const endSequence = uniqueMembers[uniqueMembers.length - 1]?.sequence || toolEvents[toolEvents.length - 1].sequence;
    return {
      groupId: `plan-group-${groupIndex + 1}-${startSequence}-${endSequence}`,
      title: groupIndex === 0 ? '制定分析任务计划' : `修订分析任务计划 ${groupIndex}`,
      summary: `创建或定义 ${tasks.length} 项任务，设置 ${dependencyCount} 条任务依赖。`,
      startSequence,
      endSequence,
      memberEventIds: uniqueMembers.map((event) => event.event_id),
      tasks,
      dependencyCount,
      status,
    };
  });
}

function hasPlanBoundaryBetween(
  events: ObserverEvent[],
  leftSequence: number,
  rightSequence: number,
): boolean {
  return events.some((event) => {
    if (event.sequence <= leftSequence || event.sequence >= rightSequence) return false;
    if (event.event_type === 'model_response') return toolUseIds(event).length === 0;
    if (event.event_type === 'tool_execution') {
      if (isPlanStructureToolEvent(event)) return false;
      const toolName = String(event.payload.name || '').toLowerCase();
      const input = asRecord(event.payload.input);
      if (toolName === 'taskupdate' && input.status) return true;
      return !['taskget', 'tasklist'].includes(toolName);
    }
    return event.event_type === 'assistant_message'
      || event.event_type === 'command_execution'
      || event.event_type === 'subagent_result'
      || event.event_type === 'user_prompt';
  });
}

function isPlanStructureToolEvent(event: ObserverEvent): boolean {
  if (event.event_type !== 'tool_execution') return false;
  const toolName = String(event.payload.name || '').toLowerCase();
  if (toolName === 'taskcreate') return true;
  if (toolName !== 'taskupdate') return false;
  const input = asRecord(event.payload.input);
  return Boolean(
    input.addBlockedBy
    || input.blockedBy
    || input.blocked_by
    || input.removeBlockedBy
    || input.subject
    || input.description
    || input.activeForm,
  ) && !input.status;
}

function buildRawTimelineItems(
  events: ObserverEvent[],
  planGroups: PlanDisplayGroup[],
): RawTimelineItem[] {
  const memberToGroup = new Map<string, PlanDisplayGroup>();
  planGroups.forEach((group) => {
    group.memberEventIds.forEach((eventId) => memberToGroup.set(eventId, group));
  });
  const inserted = new Set<string>();
  const result: RawTimelineItem[] = [];
  for (const event of events) {
    const group = memberToGroup.get(event.event_id);
    if (!group) {
      result.push({ kind: 'event', event });
      continue;
    }
    if (!inserted.has(group.groupId)) {
      result.push({ kind: 'plan_group', group });
      inserted.add(group.groupId);
    }
  }
  return result;
}

function rawEventDisplay(
  trace: ObserverTrace,
  event: ObserverEvent,
  taskRegistry: TaskRegistry,
): EventDisplayDescription {
  if (event.event_type === 'model_response') {
    const tools = resolveToolExecutions(trace, event);
    const requestedCount = toolUseIds(event).length;
    if (!requestedCount) {
      const finalAnswer = Boolean(event.payload.is_final) || event.payload.stop_reason === 'end_turn';
      return {
        typeLabel: eventTypeLabel(event.event_type),
        title: finalAnswer ? '向用户交付最终回答' : '向用户发送阶段消息',
        summary: firstString(event.payload.text, event.summary, '没有可见文字'),
        context: `${String(event.payload.model || '未知模型')} · ${humanStopReason(event.payload.stop_reason)}`,
      };
    }
    const names = tools.map((tool) => String(tool.payload.name || tool.title || 'Tool'));
    const operations = tools.map((tool) => toolOperationTitle(tool, taskRegistry));
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: `发起 ${tools.length || requestedCount} 个执行请求`,
      summary: operations.join('；') || '当前 Trace 中没有找到对应工具执行',
      context: `${String(event.payload.model || '未知模型')} · ${names.join(' · ') || 'Tool 未解析'}`,
    };
  }
  if (isExecutionEvent(event)) {
    const toolName = String(event.payload.name || event.title || 'Unknown Tool');
    const operation = describeToolOperation(
      toolName,
      asRecord(event.payload.input),
      event.payload.structured_result,
      taskRegistry,
    );
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: operation.title,
      summary: toolResultSummary(event),
      context: `Tool: ${toolName}${event.response_id ? ` · Batch ${shortId(event.response_id)}` : ''}`,
    };
  }
  if (event.event_type === 'assistant_message') {
    const finalAnswer = event.payload.stop_reason === 'end_turn';
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: finalAnswer ? '向用户交付最终回答' : '向用户发送阶段消息',
      summary: firstString(event.payload.text, event.summary, '没有可见文字'),
      context: `${String(event.payload.model || '未知模型')} · ${humanStopReason(event.payload.stop_reason)}`,
    };
  }
  if (event.event_type === 'subagent_result') {
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: firstString(event.payload.task_summary, event.title),
      summary: firstString(event.summary, event.payload.result),
      context: `Agent: ${firstString(event.payload.task_id, '未知')} · ${firstString(event.payload.status, event.status)}`,
    };
  }
  if (event.event_type === 'user_prompt') {
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: '用户提出任务或补充要求',
      summary: firstString(event.payload.content, event.summary),
      context: `${firstString(event.payload.prompt_source, '未知来源')} · ${firstString(event.payload.permission_mode, '权限模式未知')}`,
    };
  }
  if (event.event_type === 'control_event' || event.event_type === 'system_event') {
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: event.title,
      summary: event.summary || '系统或生命周期记录',
      context: firstString(event.payload.subtype, event.payload.type, 'system'),
    };
  }
  if (event.event_type === 'local_command') {
    return {
      typeLabel: eventTypeLabel(event.event_type),
      title: 'Claude 本地命令或命令输出',
      summary: firstString(event.payload.content, event.summary),
      context: 'local command',
    };
  }
  return {
    typeLabel: eventTypeLabel(event.event_type),
    title: event.title,
    summary: event.summary || '无摘要',
    context: event.origin,
  };
}

function eventTypeLabel(eventType: string): string {
  return ({
    user_prompt: '用户输入',
    model_response: '模型响应',
    tool_execution: '工具执行',
    command_execution: 'Agent Command',
    control_event: '控制事件',
    assistant_message: '助手消息',
    subagent_result: '子代理结果',
    system_event: '系统事件',
    local_command: '本地命令',
  } as Record<string, string>)[eventType] || eventType;
}

function isExecutionEvent(event: ObserverEvent): boolean {
  return event.event_type === 'tool_execution' || event.event_type === 'command_execution';
}

function toolUseIds(event: ObserverEvent): string[] {
  return Array.isArray(event.payload.tool_use_ids)
    ? event.payload.tool_use_ids.map((value: unknown) => String(value))
    : [];
}

function toolResultSummary(event: ObserverEvent): string {
  if (event.status === 'incomplete') return '尚未找到对应 Tool Result';
  const output = formatReadableValue(event.payload.output, 240).replace(/\s+/g, ' ').trim();
  if (event.status === 'error') return output ? `执行失败：${output}` : '工具执行失败';
  return output ? `执行成功：${output}` : '工具执行成功';
}

function shortId(value: string): string {
  return value.length <= 14 ? value : `${value.slice(0, 10)}…`;
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
  if (isExecutionEvent(event)) return [event];
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
      isExecutionEvent(candidate)
      && (
        invokedEventIds.has(candidate.event_id)
        || Boolean(candidate.tool_use_id && requestedToolIds.has(candidate.tool_use_id))
      )
    ))
    .sort((left, right) => left.sequence - right.sequence);
}

function toolOperationTitle(event: ObserverEvent, taskRegistry: TaskRegistry): string {
  const payload = event.payload || {};
  return describeToolOperation(
    String(payload.name || event.title || 'Unknown Tool'),
    asRecord(payload.input),
    payload.structured_result,
    taskRegistry,
  ).title;
}

function describeToolOperation(
  toolName: string,
  input: Record<string, unknown>,
  structuredResult: unknown = null,
  taskRegistry: TaskRegistry = {},
): ToolOperationDescription {
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
    const structured = asRecord(structuredResult);
    const structuredTask = asRecord(structured.task);
    const taskId = firstString(
      structuredTask.id,
      structured.taskId,
      extractTaskId(structuredResult),
    );
    const subject = firstString(input.subject, structuredTask.subject, '未命名任务');
    const description = firstString(input.description);
    const activeForm = firstString(input.activeForm);
    return {
      title: `制定计划${taskId ? ` #${taskId}` : ''}：${subject}`,
      typeLabel: '任务计划',
      summary: description || activeForm || '在任务系统中建立一个新的计划项。',
      fields: compactFields([
        ['Task ID', taskId],
        ['计划名称', subject],
        ['计划目标', description],
        ['执行中描述', activeForm],
        ['创建结果', firstString(asRecord(structuredResult).success) || (taskId ? '已创建' : '')],
      ]),
    };
  }
  if (lower === 'taskupdate') {
    const taskId = firstString(input.taskId, input.task_id, '未知任务');
    const task = taskRegistry[taskId];
    const structured = asRecord(structuredResult);
    const statusChange = asRecord(structured.statusChange);
    const dependencies = arrayStrings(input.addBlockedBy ?? input.blockedBy ?? input.blocked_by);
    const dependencyLabels = dependencies.map((dependencyId) => {
      const dependency = taskRegistry[dependencyId];
      return dependency ? `#${dependencyId} ${dependency.subject}` : `#${dependencyId}`;
    });
    const updatedFields = arrayStrings(structured.updatedFields);
    const statusFrom = firstString(statusChange.from);
    const statusTo = firstString(statusChange.to, input.status);
    const title = statusTo
      ? `${statusAction(statusTo)}任务 #${taskId}${task ? `：${task.subject}` : ''}`
      : dependencyLabels.length
      ? `设置任务 #${taskId}${task ? `“${task.subject}”` : ''}的前置依赖`
      : `修改任务 #${taskId}${task ? `：${task.subject}` : ''}`;
    const changes: string[] = [];
    if (statusTo) {
      changes.push(
        statusFrom
          ? `状态从 ${statusLabel(statusFrom)} 修改为 ${statusLabel(statusTo)}`
          : `状态修改为 ${statusLabel(statusTo)}`,
      );
    }
    if (dependencyLabels.length) {
      changes.push(`新增前置依赖：${dependencyLabels.join('、')}`);
    }
    if (input.subject) changes.push(`任务名称修改为：${String(input.subject)}`);
    if (input.description) changes.push(`任务目标修改为：${String(input.description)}`);
    if (input.activeForm) changes.push(`执行中描述修改为：${String(input.activeForm)}`);
    return {
      title,
      typeLabel: '任务更新',
      summary: changes.join('；') || '更新任务状态、依赖或描述。',
      fields: compactFields([
        ['Task ID', taskId],
        ['任务名称', task?.subject || '当前 Trace 中未找到对应 TaskCreate'],
        ['原计划目标', task?.description || ''],
        ['状态变化', statusTo ? `${statusFrom ? statusLabel(statusFrom) : '未知'} → ${statusLabel(statusTo)}` : ''],
        ['新增依赖', dependencyLabels.join('、')],
        ['修改字段', updatedFields.join('、')],
        ['新任务名称', optionalString(input.subject)],
        ['新任务目标', optionalString(input.description)],
        ['新执行描述', optionalString(input.activeForm)],
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

function arrayStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter(Boolean)
    : value === null || value === undefined || value === ''
    ? []
    : [String(value)];
}

function extractTaskId(value: unknown): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value || '');
  return text.match(/Task\s*#?(\d+)/i)?.[1] || '';
}

function statusAction(status: string): string {
  return ({
    pending: '将任务设为待处理：',
    in_progress: '开始执行',
    completed: '完成',
    deleted: '删除',
  } as Record<string, string>)[status] || '更新';
}

function statusLabel(status: string): string {
  return ({
    pending: '待处理',
    in_progress: '执行中',
    completed: '已完成',
    deleted: '已删除',
  } as Record<string, string>)[status] || status;
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

type ExecutionGraphRelation = ObserverRelation & { fallback?: boolean };

function buildExecutionRelations(
  events: ObserverEvent[],
  logicalRelations: ObserverRelation[],
): ExecutionGraphRelation[] {
  const eventIds = new Set(events.map((event) => event.event_id));
  const relations: ExecutionGraphRelation[] = logicalRelations
    .filter((relation) => eventIds.has(relation.from) && eventIds.has(relation.to))
    .map((relation) => ({ ...relation, fallback: false }));
  const logicalIncoming = new Set(relations.map((relation) => relation.to));
  const previousByTurn = new Map<string, ObserverEvent>();
  const orderedEvents = [...events].sort((left, right) => (
    left.sequence - right.sequence || left.event_id.localeCompare(right.event_id)
  ));

  orderedEvents.forEach((event) => {
    const turnId = event.turn_id || '';
    const previous = turnId ? previousByTurn.get(turnId) : undefined;
    if (
      previous
      && event.event_type !== 'user_prompt'
      && !logicalIncoming.has(event.event_id)
    ) {
      relations.push({
        relation_id: `next-fallback-${previous.event_id}-${event.event_id}`,
        from: previous.event_id,
        to: event.event_id,
        type: 'next_fallback',
        origin: 'derived',
        fallback: true,
      });
    }
    if (turnId) previousByTurn.set(turnId, event);
  });

  return relations;
}

function buildGraph(
  trace: ObserverTrace | null,
  selectedEventId: string | null,
  rawMode = false,
  taskRegistry: TaskRegistry = {},
  planGroups: PlanDisplayGroup[] = [],
  selectedPlanGroupId: string | null = null,
  onOpenArtifact: (artifactId: string) => Promise<void> = async () => {},
): { nodes: Node[]; edges: Edge[] } {
  if (!trace) return { nodes: [], edges: [] };
  const sourceEvents = trace.events.filter((event) => (
    GRAPH_EVENT_TYPES.has(event.event_type) && !event.hidden_by_default
  ));
  const memberToGroup = new Map<string, PlanDisplayGroup>();
  if (rawMode) {
    planGroups.forEach((group) => {
      group.memberEventIds.forEach((eventId) => memberToGroup.set(eventId, group));
    });
  }
  const events = sourceEvents.filter((event) => !memberToGroup.has(event.event_id));
  const eventIds = new Set(events.map((event) => event.event_id));
  const artifacts = rawMode
    ? []
    : (trace.artifacts || []).filter((artifact) => (
        artifact.operations.some((operation) => eventIds.has(operation.event_id))
      ));
  const artifactLinks = artifacts.flatMap((artifact) => (
    artifact.operations
      .filter((operation) => eventIds.has(operation.event_id))
      .map((operation) => ({ artifact, operation }))
  ));
  const visibleIds = new Set([
    ...events.map((event) => event.event_id),
    ...(rawMode ? planGroups.map((group) => group.groupId) : []),
  ]);
  const remapId = (eventId: string) => memberToGroup.get(eventId)?.groupId || eventId;
  const remappedRelations = trace.relations
    .filter((relation) => relation.type === 'next' || EXECUTION_LOGICAL_RELATIONS.has(relation.type))
    .map((relation) => ({
      ...relation,
      from: remapId(relation.from),
      to: remapId(relation.to),
    }))
    .filter((relation) => (
      relation.from !== relation.to
      && visibleIds.has(relation.from)
      && visibleIds.has(relation.to)
    ));
  const dedupedRelations = [...new Map(
    remappedRelations.map((relation) => [
      `${relation.from}|${relation.to}|${relation.type}`,
      relation,
    ]),
  ).values()];
  const logicalRelations = dedupedRelations.filter((relation) => (
    EXECUTION_LOGICAL_RELATIONS.has(relation.type)
  ));
  const relations = rawMode
    ? dedupedRelations.filter((relation) => ['next', 'invokes'].includes(relation.type))
    : buildExecutionRelations(events, logicalRelations);
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: 'TB',
    ranksep: rawMode ? 92 : 72,
    nodesep: rawMode ? 58 : 46,
    marginx: 30,
    marginy: 30,
  });
  graph.setDefaultEdgeLabel(() => ({}));
  events.forEach((event) => {
    const size = eventGraphSize(event, rawMode);
    graph.setNode(event.event_id, size);
  });
  if (rawMode) {
    planGroups.forEach((group) => graph.setNode(group.groupId, { width: 300, height: 132 }));
  }
  relations.forEach((relation) => graph.setEdge(relation.from, relation.to));
  dagre.layout(graph);

  const nodes: Node[] = events.map<Node>((event) => {
    const position = graph.node(event.event_id) || { x: 0, y: 0 };
    const colors = nodeColors(event);
    const size = eventGraphSize(event, rawMode);
    const display = rawMode
      ? rawEventDisplay(trace, event, taskRegistry)
      : {
          typeLabel: eventTypeLabel(event.event_type),
          title: event.title,
          summary: event.summary || '',
          context: '',
        };
    return {
      id: event.event_id,
      type: rawMode ? undefined : 'execution',
      position: { x: position.x - size.width / 2, y: position.y - size.height / 2 },
      data: rawMode
        ? {
            label: `${display.typeLabel.toUpperCase()} · #${event.sequence}\n${display.title}\n${truncateText(display.context || display.summary, 110)}`,
          }
        : {
            nodeKind: 'execution',
            sequence: event.sequence,
            typeLabel: eventTypeLabel(event.event_type),
            title: event.title,
            summary: event.summary || '',
            status: event.status,
            accent: colors.border,
          },
      style: rawMode
        ? {
            width: size.width,
            minHeight: size.height,
            whiteSpace: 'pre-wrap',
            textAlign: 'left',
            fontSize: 11,
            lineHeight: 1.45,
            borderRadius: event.event_type === 'model_response' ? 28 : 16,
            borderWidth: selectedEventId === event.event_id ? 3 : 2,
            borderColor: colors.border,
            background: colors.background,
            color: '#2b2520',
            boxShadow: selectedEventId === event.event_id
              ? '0 12px 28px rgba(217,119,69,0.2)'
              : '0 8px 20px rgba(76,55,32,0.08)',
          }
        : {
            width: size.width,
            height: size.height,
          },
    };
  });
  if (rawMode) {
    planGroups.forEach((group) => {
      const position = graph.node(group.groupId) || { x: 0, y: 0 };
      nodes.push({
        id: group.groupId,
        position: { x: position.x - 150, y: position.y - 66 },
        data: {
          label: `展示分组 · 任务规划\n${group.title}\n${group.tasks.length} 项任务 · ${group.dependencyCount} 条依赖 · ${group.memberEventIds.length} Events`,
        },
        style: {
          width: 300,
          minHeight: 132,
          whiteSpace: 'pre-wrap',
          textAlign: 'left',
          fontSize: 11,
          lineHeight: 1.5,
          borderRadius: 20,
          borderWidth: selectedPlanGroupId === group.groupId ? 3 : 2,
          borderColor: group.status === 'error' ? '#dc2626' : '#7c3aed',
          background: group.status === 'error' ? '#fff1f2' : '#f5f3ff',
          color: '#2b2520',
          boxShadow: selectedPlanGroupId === group.groupId
            ? '0 12px 28px rgba(124,58,237,0.2)'
            : '0 8px 20px rgba(76,55,32,0.08)',
        },
      });
    });
  }
  artifacts.forEach((artifact) => {
    const primaryLink = artifactLinks.find(
      (item) => item.artifact.artifact_id === artifact.artifact_id,
    );
    const producerPosition = primaryLink
      ? graph.node(primaryLink.operation.event_id)
      : { x: 0, y: 0 };
    const producerEvent = primaryLink
      ? events.find((event) => event.event_id === primaryLink.operation.event_id)
      : undefined;
    const producerSize = producerEvent
      ? eventGraphSize(producerEvent, rawMode)
      : { width: 240, height: 104 };
    const siblings = primaryLink
      ? artifactLinks.filter(
          (item) => item.operation.event_id === primaryLink.operation.event_id,
        )
      : [];
    const index = Math.max(
      0,
      siblings.findIndex((item) => item.artifact.artifact_id === artifact.artifact_id),
    );
    const rowCount = Math.ceil(Math.max(1, siblings.length) / 2);
    const column = index % 2;
    const row = Math.floor(index / 2);
    nodes.push({
      id: artifact.artifact_id,
      type: 'artifact',
      position: {
        x: producerPosition.x + producerSize.width / 2 + 60 + column * (ARTIFACT_NODE_WIDTH + 20),
        y: producerPosition.y - ARTIFACT_NODE_HEIGHT / 2 + (row - (rowCount - 1) / 2) * 88,
      },
      data: {
        nodeKind: 'artifact',
        name: fileName(artifact.name || artifact.path),
        path: artifact.path,
        exists: artifact.exists,
        accent: artifactColor(artifact.artifact_type),
        onOpen: () => void onOpenArtifact(artifact.artifact_id),
      },
      style: {
        width: ARTIFACT_NODE_WIDTH,
        height: ARTIFACT_NODE_HEIGHT,
      },
    });
  });
  const edges: Edge[] = relations
    .map((relation) => {
      const fallback = relation.type === 'next_fallback';
      const rawInvoke = rawMode && relation.type === 'invokes';
      const stroke = rawInvoke ? '#8b5cf6' : fallback ? '#d9b49d' : '#d97745';
      return {
        id: `${relation.relation_id}-${relation.from}-${relation.to}`,
        source: relation.from,
        target: relation.to,
        sourceHandle: rawMode ? undefined : 'main-out',
        targetHandle: rawMode ? undefined : 'main-in',
        label: rawMode ? (relation.type === 'invokes' ? 'INVOKES' : relation.type) : undefined,
        type: 'smoothstep',
        animated: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: stroke,
        },
        style: {
          stroke,
          strokeWidth: fallback ? 1.35 : 2.1,
          opacity: fallback ? 0.72 : 0.9,
        },
        labelStyle: { fontSize: 9, fill: '#78695c' },
      };
    });
  artifactLinks.forEach(({ artifact, operation }) => {
    edges.push({
      id: `artifact-edge-${operation.event_id}-${artifact.artifact_id}`,
      source: operation.event_id,
      target: artifact.artifact_id,
      sourceHandle: 'artifact-out',
      targetHandle: 'artifact-in',
      label: operation.operation === 'modified' ? '修改' : '生成',
      type: 'smoothstep',
      animated: false,
      style: { stroke: artifactColor(artifact.artifact_type), strokeWidth: 1.8 },
      labelStyle: { fontSize: 9, fill: '#57534e' },
    });
  });
  return { nodes, edges };
}

function artifactColor(type: string): string {
  if (type === 'dataset') return '#2563eb';
  if (type === 'report') return '#d97745';
  if (type === 'visualization') return '#7c3aed';
  if (type === 'code') return '#0f766e';
  return '#78716c';
}

function eventGraphSize(event: ObserverEvent, rawMode: boolean): { width: number; height: number } {
  if (!rawMode) return { width: EXECUTION_NODE_WIDTH, height: EXECUTION_NODE_HEIGHT };
  if (event.event_type === 'model_response') return { width: 220, height: 94 };
  if (isExecutionEvent(event)) return { width: 280, height: 122 };
  if (event.event_type === 'subagent_result') return { width: 280, height: 116 };
  return { width: 250, height: 106 };
}

function executionStatusDisplay(status: string): { label: string; color: string } {
  if (status === 'error') return { label: '失败', color: '#b91c1c' };
  if (status === 'incomplete') return { label: '未完成', color: '#b45309' };
  if (status === 'running' || status === 'in_progress') return { label: '执行中', color: '#2563eb' };
  if (status === 'success' || status === 'complete' || status === 'completed') return { label: '完成', color: '#15803d' };
  if (status === 'observed') return { label: '已观察', color: '#78716c' };
  return { label: status || '已记录', color: '#78716c' };
}

function nodeColors(event: ObserverEvent): { border: string; background: string } {
  if (event.status === 'error') return { border: '#dc2626', background: '#fff1f2' };
  if (event.event_type === 'user_prompt') return { border: '#0f766e', background: '#f0fdfa' };
  if (event.event_type === 'model_response') return { border: '#2563eb', background: '#eff6ff' };
  if (event.event_type === 'tool_execution') return { border: '#8b5cf6', background: '#f5f3ff' };
  if (event.event_type === 'command_execution') return { border: '#d97745', background: '#fff7ed' };
  if (event.event_type === 'subagent_result') return { border: '#0891b2', background: '#ecfeff' };
  if (event.event_type === 'control_event') return { border: '#b45309', background: '#fffbeb' };
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
