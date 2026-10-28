import { useCallback, useEffect, useRef, useState } from 'react';
import { ObserverMetrics, ObserverSessionSummary, ObserverTrace, LiveTraceState } from '../types/observer';
import { SemanticProgress, SemanticWorkflow } from '../types/semantic';
import SemanticWorkflowView from '../components/SemanticWorkflowView';
import TranscriptView from '../components/TranscriptView';
import ExecutionWorkflowView from '../components/ExecutionWorkflowView';
import { normalizeObserverTrace } from '../utils/observer';

type ObserverView = 'semantic' | 'execution' | 'raw';

interface ObserverPageProps {
  view: ObserverView;
  onViewChange: (view: ObserverView) => void;
  requestedSessionId: string | null;
  sessionRequestVersion: number;
}

export default function ObserverPage({ view, onViewChange, requestedSessionId, sessionRequestVersion }: ObserverPageProps) {
  const traceRequestRef = useRef(0);
  const [sessions, setSessions] = useState<ObserverSessionSummary[]>([]);
  const [liveState, setLiveState] = useState<LiveTraceState | null>(null);
  const [trace, setTrace] = useState<ObserverTrace | null>(null);
  const [semanticWorkflow, setSemanticWorkflow] = useState<SemanticWorkflow | null>(null);
  const [semanticProgress, setSemanticProgress] = useState<SemanticProgress | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [localMetrics, setLocalMetrics] = useState<ObserverMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [executionActions, setExecutionActions] = useState<HTMLDivElement | null>(null);
  const [executionStatus, setExecutionStatus] = useState<HTMLDivElement | null>(null);

  const loadTrace = useCallback(async (sessionId: string) => {
    const requestId = ++traceRequestRef.current;
    setSelectedSessionId(sessionId);
    setTrace(null);
    setLiveState(null);
    setSemanticWorkflow(null);
    setSemanticProgress(null);
    setSelectedEventId(null);
    setLocalMetrics(null);
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/trace`);
      if (requestId !== traceRequestRef.current) return;
      if (response.status === 404) return;
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      const value = normalizeObserverTrace(await response.json() as ObserverTrace);
      if (requestId !== traceRequestRef.current) return;
      setTrace(value);
      setSelectedSessionId(sessionId);
      setSemanticProgress(null);
      setSelectedEventId(null);
      const semanticResponse = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/semantic`);
      if (semanticResponse.ok) {
        const workflow = normalizeSemanticWorkflow(await semanticResponse.json());
        if (requestId !== traceRequestRef.current) return;
        setSemanticWorkflow(workflow);
      } else {
        if (requestId !== traceRequestRef.current) return;
        setSemanticWorkflow(null);
      }
      const progressResponse = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/semantic/progress`);
      if (progressResponse.ok) {
        const progress = await progressResponse.json() as SemanticProgress;
        if (requestId !== traceRequestRef.current) return;
        setSemanticProgress(progress);
      }
    } catch (loadError) {
      if (requestId === traceRequestRef.current) setError(loadError instanceof Error ? loadError.message : '无法读取会话记录');
    } finally {
      if (requestId === traceRequestRef.current) setLoading(false);
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
      const first = (body.sessions || []).find((item) => item.derived) || body.sessions?.[0];
      if (first && !selectedSessionId && !requestedSessionId) await loadTrace(first.session_id);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '无法列出 Observation');
    } finally {
      setLoading(false);
    }
  }, [loadTrace, selectedSessionId, requestedSessionId]);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    if (requestedSessionId) void loadTrace(requestedSessionId);
  }, [requestedSessionId, sessionRequestVersion, loadTrace]);

  useEffect(() => {
    if (!selectedSessionId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let revision = -1;
    const sessionId = selectedSessionId;
    const requestId = traceRequestRef.current;
    const poll = async () => {
      try {
        const response = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/live`, {cache:'no-store'});
        if (!response.ok) return;
        const state = await response.json() as LiveTraceState;
        if (!active || requestId !== traceRequestRef.current || (!state.enabled && state.analysis_mode !== 'manual')) return;
        setLiveState(state);
        if (state.trace_revision !== revision) {
          const result = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/trace`, {cache:'no-store'});
          if (result.ok && active && requestId === traceRequestRef.current) {
            const value = normalizeObserverTrace(await result.json() as ObserverTrace);
            if (active && requestId === traceRequestRef.current) {setTrace(value); revision=state.trace_revision;}
          }
        }
      } catch { /* Retry publication/network errors without clearing the graph. */ }
      finally { if (active) timer=setTimeout(poll,1500); }
    };
    void poll();
    return () => {active=false; clearTimeout(timer);};
  }, [selectedSessionId, sessionRequestVersion]);

  const handleUpload = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const value = JSON.parse(await file.text()) as ObserverTrace;
      if (!['observer-trace/1.0', 'observer-trace/2.0'].includes(value.schema_version) || !Array.isArray(value.events)) {
        throw new Error('请选择 derive 生成的 observer_trace.json');
      }
      setTrace(normalizeObserverTrace(value));
      setSemanticWorkflow(null);
      setSemanticProgress(null);
      setSelectedSessionId(value.session.session_id);
        setSelectedEventId(null);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : '文件解析失败');
    } finally {
      setLoading(false);
    }
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
    onViewChange('raw');
  }, [onViewChange]);
  const focusLines = trace?.events.find((event) => event.event_id === selectedEventId)?.source_lines || [];

  return (
    <div className="h-full flex flex-col bg-[#fffaf5]">
      <header className={`shrink-0 flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2 border-b border-line bg-white/60 ${view === 'execution' ? 'observer-execution-header' : ''}`}>
        <div className="observer-page-heading min-w-0">
          <h1 className="text-base font-semibold">{view === 'raw' ? '原始 Transcript' : view === 'execution' ? 'Agent 详细执行工作流' : '工作流可视化'}</h1>
          {view === 'semantic' && <p className="hidden sm:block text-[11px] text-muted mt-1">按输入、规划、执行、修改梳理过程，展开语义块查看原阶段与证据</p>}
        </div>
        {view === 'execution' && <div ref={setExecutionActions} className="execution-header-actions-slot" />}
        {view === 'raw' && <MetricStrip metrics={localMetrics || trace?.metrics} />}
        <select
          aria-label="选择会话"
          value={selectedSessionId || ''}
          onChange={(event) => event.target.value && void loadTrace(event.target.value)}
          className="ml-auto w-[170px] sm:w-[240px] max-w-full px-3 py-1.5 rounded-lg border border-line bg-white text-[11px] font-mono"
        >
          <option value="">选择会话</option>
          {sessions.map((session) => (
            <option key={session.session_id} value={session.session_id}>{session.session_id}</option>
          ))}
        </select>
        {view !== 'raw' && (
          <label className="px-3 py-2 rounded-xl border border-line-strong bg-white text-xs cursor-pointer hover:border-accent whitespace-nowrap">
            导入记录
            <input type="file" accept="application/json,.json" className="hidden" onChange={(event) => void handleUpload(event.target.files?.[0])} />
          </label>
        )}
        <button type="button" onClick={() => void refreshSessions()} className="px-3 py-1.5 rounded-lg border border-line-strong bg-white text-xs hover:border-accent">刷新会话</button>
        {view === 'execution' && <div ref={setExecutionStatus} className="execution-header-status-slot" />}
      </header>

      {error && (
        <div className="mx-4 mt-3 px-4 py-2 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {view === 'semantic' ? (
        <div className="flex-1 min-h-0">
          {trace ? (
            <SemanticWorkflowView
              trace={trace}
              workflow={semanticWorkflow}
              loading={loading}
              progress={semanticProgress}
              onGenerate={generateSemantic}
              onEvidence={openEvidence}
              onOpenArtifact={openLocalArtifact}
            />
          ) : (
            <div className="h-full flex items-center justify-center p-8 text-sm text-muted text-center">
              {loading ? '正在读取工作流…' : '选择一次会话，或导入已有的分析记录。'}
            </div>
          )}
        </div>
      ) : view === 'execution' ? (
        <div className="flex-1 min-h-0">
          {trace ? (
            <ExecutionWorkflowView key={trace.session.session_id} trace={trace} liveState={liveState} onEvidence={openEvidence} onOpenArtifact={openLocalArtifact} headerActions={executionActions} headerStatus={executionStatus} />
          ) : (
            <div className="h-full flex items-center justify-center p-8 text-sm text-muted text-center">
              {loading ? '正在读取执行记录…' : '选择一次会话，或导入已有的执行记录。'}
            </div>
          )}
        </div>
      ) : (
        <main className="flex-1 min-h-0 flex flex-col p-2 lg:p-3">
          <section className="flex-1 min-h-0 border border-line rounded-2xl bg-white overflow-hidden shadow-sm">
            <TranscriptView sessionId={selectedSessionId} focusLines={focusLines} turnCount={trace?.metrics.human_prompt_count} refreshRevision={liveState?.enabled ? liveState.trace_revision : undefined} onLocalMetricsChange={setLocalMetrics} />
          </section>
        </main>
      )}
    </div>
  );
}

function MetricStrip({ metrics }: { metrics?: ObserverMetrics }) {
  const values = [
    ['Turns', metrics?.human_prompt_count ?? 0],
    ['Tools', metrics?.tool_call_count ?? 0],
    ['Subagents', metrics?.subagent_result_count ?? 0],
    ['Errors', metrics?.tool_error_count ?? 0],
    ['Tool time', formatDuration(metrics?.total_tool_duration_ms)],
    ['Cost', formatCost(metrics?.total_cost_usd)],
  ];
  return (
    <dl aria-label="会话统计" className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {values.map(([label, value]) => (
        <div key={String(label)} className="flex items-baseline gap-1.5 whitespace-nowrap">
          <dt className="text-[10px] text-muted">{label}</dt>
          <dd className="ot-stat text-sm font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatDuration(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(2)}s`;
}

function formatCost(value?: number | null): string {
  return value === null || value === undefined ? '—' : `$${value.toFixed(3)}`;
}

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
