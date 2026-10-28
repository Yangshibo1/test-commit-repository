import { memo, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactFlow, { Background, BaseEdge, Edge, EdgeProps, EdgeLabelRenderer, Handle, MarkerType, MiniMap, Node, NodeProps, Position, ReactFlowInstance, useViewport } from 'reactflow';
import 'reactflow/dist/style.css';
import { ObserverEvent, ObserverTrace, LiveTraceState } from '../types/observer';
import './SemanticWorkflowView.css';
import EventArtifactBadges, { ArtifactIcon, EventArtifactList } from './EventArtifactBadges';
import { artifactCategories, indexEventArtifacts } from '../utils/eventArtifacts';
import EventFeedbackPanel from './EventFeedbackPanel';
import type { EventArtifactLink } from '../utils/eventArtifacts';
import { EventWorkflow, EventWorkflowProgress, EventImportanceLevel } from '../types/eventWorkflow';
import { layoutEventTurns } from '../utils/eventTurns';
import { attachRoutePorts, routeEventRelations, sharedChannelDashOffset } from '../utils/eventRouting';
import { eventBehaviorRoles, eventRoleColor, eventRoleLabel, isKeyEvent, isRoutineEvent, eventRelationLabels, mergeEventRelations, validateImportedEventWorkflow, validateLiveEventWorkflow } from '../utils/eventWorkflow';

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

const EXECUTION_READING_ZOOM = 0.82;
const EXECUTION_NODE_WIDTH = 276;
const EXECUTION_NODE_HEIGHT = 124;

interface ExecutionGraphNodeData {
  nodeKind: 'execution';
  sequence: number;
  typeLabel: string;
  title: string;
  summary: string;
  status: string;
  accent: string;
  importance?: EventImportanceLevel;
  weighted?: boolean;
  artifacts: EventArtifactLink[];
  onOpenArtifact: (id: string) => void;
  onInspectArtifacts: () => void;
}

const ExecutionGraphNode = memo(({ data, selected }: NodeProps<ExecutionGraphNodeData>) => {
  const { zoom } = useViewport();
  const small = data.weighted && data.importance === 'background';
  const support = data.weighted && isRoutineEvent(data.importance);
  const status = executionStatusDisplay(data.status);
  return (
    <div className={`relative h-full w-full overflow-hidden rounded-xl border bg-[#fffdfb] ${selected ? 'border-accent shadow-md' : 'border-[#e7ded3] shadow-sm'}`}
      style={{ borderLeftWidth: small ? 2 : 4, borderLeftColor: small ? '#b6ada3' : data.accent }}
      title={`${data.sequence} · ${data.title} · ${importanceLabel(data.importance)}`}>
      <div className={`flex h-full flex-col ${small ? 'px-3 py-2' : 'px-4 py-3'} ${data.artifacts.length ? '!pb-9' : ''}`}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold tabular-nums" style={{ color: data.accent }}>{String(data.sequence).padStart(2, '0')}</span>
          <span className="truncate text-[10px] text-muted">{data.typeLabel}</span>
          {data.importance && <span className={`ml-auto text-[10px] whitespace-nowrap ${isKeyEvent(data.importance) ? 'font-semibold' : ''}`} style={{color:eventRoleColor(data.importance)}}>{importanceLabel(data.importance)}</span>}
        </div>
        <div className={`${small ? 'mt-1 truncate text-xs' : support ? 'mt-2 line-clamp-2 text-sm' : 'mt-2 line-clamp-2 text-[15px]'} font-semibold leading-5`}>{data.title}</div>
        {!small && !support && zoom >= .6 && <div className="mt-2 line-clamp-2 text-[11px] text-muted leading-4">{data.summary}</div>}
        {!small && <span className="mt-auto pt-1 text-[10px]" style={{ color: status.color }}>{status.label}</span>}
      </div>
      <EventArtifactBadges links={data.artifacts} onOpen={data.onOpenArtifact} onMore={data.onInspectArtifacts} />
      <Handle type="target" position={Position.Top} id="main-in" className="!opacity-0" />
      <Handle type="source" position={Position.Bottom} id="main-out" className="!opacity-0" />
      {(['left','right'] as const).map(side=><span key={side}>
        <Handle type="source" position={side==='left'?Position.Left:Position.Right} id={`lateral-out-${side}`} className="!opacity-0" />
        <Handle type="target" position={side==='left'?Position.Left:Position.Right} id={`lateral-in-${side}`} className="!opacity-0" />
      </span>)}

    </div>
  );
});

ExecutionGraphNode.displayName = 'ExecutionGraphNode';

const executionNodeTypes = {
  execution: ExecutionGraphNode,
  turnLabel: memo(({ data }: NodeProps<{ nodeKind: 'turnLabel'; ordinal: number; title: string; count: number; statusText?: string }>) => (
    <div className="event-turn-label"><span className="event-turn-number">{data.ordinal ? `Turn ${data.ordinal}` : '未归属 Turn'}</span><span className="event-turn-prompt" title={data.title}>{data.title}</span><span className="event-turn-count">{data.count} 个事件</span>{data.statusText && <span className="event-turn-live-status">{data.statusText}</span>}</div>
  )),
};

const StoryRelationEdge = memo(({ id, sourceX, sourceY, targetX, targetY, data, markerEnd, style }: EdgeProps) => {
  const points = attachRoutePorts(data.route.points, {x:sourceX,y:sourceY}, {x:targetX,y:targetY});
  const path = points.map((point: {x: number; y: number}, index: number) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
  const label = data.route.labelPosition;
  return <><BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ ...style, strokeLinejoin: 'round', strokeLinecap: 'round', strokeDashoffset: sharedChannelDashOffset(points, data.route.sharedChannelY) }} />
    {data.shortLabel && label && <EdgeLabelRenderer><button type="button" className={`nodrag nopan event-edge-label ${data.logical ? '' : 'is-rule'}`} title={data.fullLabel}
      style={{ transform: `translate(-50%, -50%) translate(${label.x}px,${label.y}px)`, pointerEvents: 'all' }} onClick={data.onSelect}>{data.shortLabel}</button></EdgeLabelRenderer>}</>;
});
const executionEdgeTypes = { story: StoryRelationEdge };

interface ExecutionWorkflowViewProps {
  trace: ObserverTrace;
  liveState?: LiveTraceState | null;
  onEvidence: (eventId: string) => void;
  onOpenArtifact: (artifactId: string) => Promise<void>;
  headerActions: HTMLElement | null;
  headerStatus: HTMLElement | null;
}

export default function ExecutionWorkflowView({ trace, liveState, onEvidence, onOpenArtifact, headerActions, headerStatus }: ExecutionWorkflowViewProps) {
  const events = useMemo(() => trace.events.filter((event) => GRAPH_EVENT_TYPES.has(event.event_type) && !event.hidden_by_default)
    .sort((left, right) => left.sequence - right.sequence), [trace.events]);
  const [selectedId, setSelectedId] = useState<string | null>(events[0]?.event_id || null);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null);
  const [zoom, setZoom] = useState(EXECUTION_READING_ZOOM);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [selectedTurns, setSelectedTurns] = useState<string[]>([]);
  const [forceTurns, setForceTurns] = useState(false);
  const [fullSessionMode, setFullSessionMode] = useState(false);
  const [workflow, setWorkflow] = useState<EventWorkflow | null>(null);
  const [progress, setProgress] = useState<EventWorkflowProgress | null>(null);
  const [weighted, setWeighted] = useState(true);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [pendingFocus, setPendingFocus] = useState<string | null>(null);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [artifactFilter, setArtifactFilter] = useState('all');
  const artifactIndex = useMemo(() => indexEventArtifacts(trace), [trace]);
  const [moreActionsOpen, setMoreActionsOpen] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const live = liveState && (liveState.enabled || liveState.analysis_mode === 'manual') ? liveState : trace.live && (trace.live.enabled || trace.live.analysis_mode === 'manual') ? trace.live : null;
  const activeAnalysis = live?.active_analysis?.status === 'running' ? live.active_analysis : null;
  const busy = submitting || ['scheduled', 'running'].includes(progress?.status || '');
  const legacyWorkflow = workflow?.schema_version === 'event-workflow/0.1';
  const legacyClassification = !!workflow && workflow.schema_version !== 'event-workflow/0.3';
  const assessedRelations = workflow?.relation_assessments || workflow?.logical_relations || [];
  const endpoint = `/api/observations/${encodeURIComponent(trace.session.session_id)}/event-workflow`;
  const behaviors = useMemo(() => new Map(workflow?.event_summaries.map(item => [item.event_id, item]) || []), [workflow]);
  const importance = useMemo(() => new Map(workflow?.event_importance.map(item => [item.event_id, item]) || []), [workflow]);

  useEffect(() => {
    if (live) return;
    let active = true;
    void Promise.all([fetch(endpoint), fetch(endpoint + '/progress')]).then(async ([result, state]) => {
      const value = result.ok ? await result.json() as EventWorkflow : null;
      const update = state.ok ? await state.json() as EventWorkflowProgress : null;
      if (!active) return;
      if (value) setWorkflow(validateImportedEventWorkflow(value, trace));
      if (update) setProgress(update);
    }).catch(error => { if (active) setAnalysisError(String(error)); });
    return () => { active = false; };
  }, [endpoint, trace, !!live]);

  useEffect(() => {
    if (!live || fullSessionMode) return;
    let active=true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response=await fetch(`/api/observations/${encodeURIComponent(trace.session.session_id)}/live/event-workflow`,{cache:'no-store'});
        if (!response.ok) return;
        const value=await response.json() as EventWorkflow | null;
        if (!active) return;
        if (value) setWorkflow(validateLiveEventWorkflow(value,trace));
        else setWorkflow(null);
        setAnalysisError(null);
      } catch { /* A result may be published just ahead of its trace refresh. */ }
      finally {if(active)timer=setTimeout(poll,1500);}
    };
    void poll();
    return () => {active=false;clearTimeout(timer);};
  }, [endpoint, trace, !!live, fullSessionMode]);

  useEffect(() => {
    if ((live && !fullSessionMode) || !['scheduled', 'running'].includes(progress?.status || '')) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await fetch(endpoint + '/progress');
        if (!response.ok) throw new Error('无法读取 Event 分析进度');
        const update = await response.json() as EventWorkflowProgress;
        if (!active) return;
        if (update.status === 'ready') {
          const result = await fetch(endpoint);
          if (!result.ok) throw new Error('无法读取 Event 分析结果');
          const value = await result.json() as EventWorkflow;
          if (active) { setWorkflow(validateImportedEventWorkflow(value, trace)); setProgress(update); }
        } else if (update.status === 'partial') {
          setProgress(update);
          setAnalysisError(update.error || '分析未完成，可从检查点继续');
        } else { setProgress(update); timer = setTimeout(poll, 1100); }
      } catch (error) { if (active) { setAnalysisError(String(error)); setProgress(current => current ? { ...current, status: 'partial', error: String(error) } : current); } }
    };
    timer = setTimeout(poll, 600);
    return () => { active = false; clearTimeout(timer); };
  }, [endpoint, progress?.status, trace, !!live, fullSessionMode]);

  const openAnalysis = () => {
    const candidates=trace.turns.filter(t=>live?.turns.find(s=>s.turn_id===t.turn_id)?.analysis_state!=='ready');
    const current=events.find(e=>e.event_id===selectedId);
    const currentTurn=current?.scope?.turn_id||current?.turn_id;
    const chosen=candidates.find(t=>t.turn_id===currentTurn)||candidates[candidates.length-1]||trace.turns[trace.turns.length-1];
    setSelectedTurns(chosen?[chosen.turn_id]:[]);setForceTurns(false);
    setAnalysisOpen(true);
  };
  const analyzeSelected = async () => {
    setSubmitting(true);setAnalysisError(null);
    try {
      const response=await fetch(`/api/observations/${encodeURIComponent(trace.session.session_id)}/live/analyze`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turn_ids:selectedTurns,force:forceTurns}),
      });
      const result=await response.json();
      if(!response.ok)throw new Error(result.detail || '提交分析失败');
      setFullSessionMode(false);setWorkflow(null);setProgress(null);setAnalysisOpen(false);
    } catch(error){setAnalysisError(String(error));}
    finally{setSubmitting(false);}
  };
  const importWorkflow = async (file?: File) => {
    if (!file) return;
    try { setWorkflow(validateImportedEventWorkflow(JSON.parse(await file.text()), trace)); setFullSessionMode(!!live); setAnalysisError(null); }
    catch (error) { setAnalysisError(String(error)); }
  };
  const selectEdge = (id: string) => { setSelectedEdgeId(id); setSelectedId(null); setDetailsOpen(true); };
  const inspectArtifacts = (id: string) => { setSelectedEdgeId(null); setSelectedId(id); setDetailsOpen(true); setShowArtifacts(false); };
  const graph = useMemo(() => buildExecutionGraph(trace, events, onOpenArtifact, workflow, weighted, selectEdge, artifactIndex.byEvent, inspectArtifacts), [trace, events, onOpenArtifact, workflow, weighted, artifactIndex]);
  const displayNodes = useMemo(() => graph.nodes.map(node => {
    if (node.data.nodeKind === 'execution') return {...node,selected:node.id===selectedId};
    const turn=live?.turns.find(t=>t.turn_id===node.data.turnId);
    if (!turn) return node;
    const statusText=activeAnalysis?.turn_id===turn.turn_id ? `分析 v${activeAnalysis.revision} · ${activeAnalysis.percent}%` : turn.execution_state === 'running' ? '执行中' : turn.execution_state === 'settling' ? '收尾中'
      : ({idle:'未分析',waiting:'未分析',historical:'历史',queued:'待分析',running:`分析 ${turn.percent||0}%`,ready:'已分析',partial:'分析失败',waiting_config:'待配置'})[turn.analysis_state];
    return {...node,data:{...node.data,statusText}};
  }), [graph.nodes,selectedId,live,activeAnalysis]);
  const displayEdges = useMemo(() => graph.edges.map(edge => edge.id === selectedEdgeId
    ? {...edge, selected:true, zIndex:6, style:{...edge.style, strokeWidth:3.5, filter:'drop-shadow(0 0 2px white)'}}
    : edge), [graph.edges, selectedEdgeId]);
  const selected = events.find((event) => event.event_id === selectedId) || null;
  const selectedEdge = graph.story.edges.find(edge => edge.id === selectedEdgeId);
  const firstTurn = graph.turns[0];
  const initialReadingNodes = firstTurn ? graph.nodes.filter(node => node.id === firstTurn.id || node.data.turnId === firstTurn.id).slice(0, firstTurn.events.length <= 5 ? 6 : 4) : [];
  const focus = (eventId: string) => {
    setSelectedEdgeId(null); setSelectedId(eventId);
    setPendingFocus(eventId);
  };
  useEffect(() => {
    if (!pendingFocus || !flow) return;
    const target = graph.nodes.find(node => node.id === pendingFocus);
    if (!target) return;
    const parent = target.parentNode ? graph.nodes.find(node => node.id === target.parentNode) : null;
    void flow.setCenter(target.position.x + (parent?.position.x || 0) + Number(target.style?.width || EXECUTION_NODE_WIDTH) / 2,
      target.position.y + (parent?.position.y || 0) + Number(target.style?.height || EXECUTION_NODE_HEIGHT) / 2, { zoom: EXECUTION_READING_ZOOM, duration: 300 });
    setPendingFocus(null);
  }, [pendingFocus, graph, flow]);

  return (
    <div className="semantic-workspace event-workspace">
      {headerActions && createPortal(<div className="event-header-actions" aria-label="执行工作流操作">
        <button type="button" className="semantic-button semantic-button-accent" disabled={submitting} onClick={openAnalysis}>语义分析</button>
        <button type="button" className="semantic-button" aria-pressed={showArtifacts} onClick={() => { setShowArtifacts(!showArtifacts); setDirectoryOpen(false); setMoreActionsOpen(false); }}>产物目录 · {artifactIndex.artifacts.length}</button>
        <button type="button" className="semantic-button event-more-button" aria-expanded={moreActionsOpen} onClick={() => setMoreActionsOpen(!moreActionsOpen)}>更多</button>
        <div className={`event-secondary-actions ${moreActionsOpen ? 'is-open' : ''}`}>
          <label className="semantic-button cursor-pointer">导入 AI 结果<input type="file" accept=".json" className="hidden" onChange={event => { void importWorkflow(event.target.files?.[0]); setMoreActionsOpen(false); }} /></label>
          <button type="button" className="semantic-button" disabled={!workflow} aria-pressed={weighted && !!workflow} onClick={() => { setWeighted(!weighted); setMoreActionsOpen(false); }}>突出关键事件</button>
          <button type="button" className="semantic-button" aria-pressed={directoryOpen} onClick={() => { setDirectoryOpen(!directoryOpen); setShowArtifacts(false); setMoreActionsOpen(false); }}>事件目录</button>
          <button type="button" className="semantic-button" aria-pressed={detailsOpen} onClick={() => { setDetailsOpen(!detailsOpen); setMoreActionsOpen(false); }}>事件详情</button>
        </div>
      </div>, headerActions)}
      {headerStatus && createPortal(<div className="execution-header-status" aria-label="Event 分析状态">
        <span className="execution-session-counts">{graph.turns.filter(turn => turn.turn_id).length} 轮 · {events.length} 个事件 · {artifactIndex.artifacts.length} 个文件</span>
        {live && <details className="execution-analysis-details"><summary>{live.enabled ? '动态采集 · 手动分析' : '手动分析'} · {live.turns.filter(t=>t.analysis_state==='ready').length}/{live.turns.length} 轮已分析{activeAnalysis ? ` · 分析中 ${activeAnalysis.percent}%` : ''}</summary><div>
          <p>逐轮分析 · 跨轮暂展示规则关系</p>
          {activeAnalysis && <p role="status">正在处理 v{activeAnalysis.revision} · {activeAnalysis.message} · {activeAnalysis.percent}%</p>}
          {live.turns.map(t=><p key={t.turn_id}>Turn {t.ordinal} · {({running:'执行中',settling:'收尾中',completed:'已完成',failed:'执行失败',interrupted:'部分执行'})[t.execution_state]} · {({idle:'未分析',waiting:'未分析',historical:'历史记录',queued:'排队中',running:`分析中 ${t.percent||0}%`,ready:'分析完成',partial:'分析失败，可重试',waiting_config:'等待 API 配置'})[t.analysis_state]}{t.revision ? ` · v${t.revision}` : ''}{!!t.boundary?.pending_background_tasks && <span> · 结束时有 {t.boundary.pending_background_tasks} 个后台任务</span>}{t.error && <span> · {t.error}</span>}</p>)}
        </div></details>}
        {(workflow || progress) && <>
          <span>{workflow?.inference_run.model || progress?.model} · 思考强度 {(workflow?.inference_run.reasoning_effort || progress?.reasoning_effort) === 'medium' ? '中' : workflow?.inference_run.reasoning_effort || progress?.reasoning_effort || '默认'}</span>
          {busy ? <span role="status">{progress?.message} · {progress?.percent || 0}% · {progress?.completed_events || 0}/{events.length} 个事件</span> : workflow && <span>逻辑关系 {workflow.logical_relations.length}</span>}
          <details className="execution-analysis-details"><summary>分析详情</summary><div>
            {trace.session.session_id === 'demo-event-workflow' && <p>演示会话 · 人工构造数据</p>}
            {workflow && <>
              <p>{(legacyClassification ? ['core', 'supporting', 'background'] as const : eventBehaviorRoles).map(level => `${importanceLabel(level)} ${workflow.event_importance.filter(item => item.level === level).length}`).join(' · ')}</p>
              {legacyClassification && <p>旧版三级评级 · 按新分类生成后更新</p>}
              <p>{legacyWorkflow ? '旧版六类关系 · 可按新规范推断' : `13 类规范 · 候选 ${workflow.validation.candidate_relation_count || 0} · 未通过 ${workflow.validation.rejected_relation_count || 0}`}</p>
              <p>{workflow.inference_run.call_count} 次调用 · {Math.round(workflow.inference_run.elapsed_seconds || 0)} 秒</p>
              <p>{legacyWorkflow ? '逻辑关系为模型推断，原始引文已校验' : '主图仅展示审查通过的推断关系'}</p>
            </>}
          </div></details>
        </>}
        <div className="event-artifact-legend" aria-label="产物类型">{artifactCategories.map(category => <span key={category.type} style={{ color: category.color }}><ArtifactIcon type={category.type} />{category.label}</span>)}</div>
      </div>, headerStatus)}
      {analysisOpen && <div className="event-analysis-backdrop" onClick={()=>!submitting&&setAnalysisOpen(false)}>
        <section role="dialog" aria-modal="true" aria-label="选择 Turn 进行语义分析" className="event-analysis-dialog" onClick={e=>e.stopPropagation()}>
          <div className="semantic-panel-heading">语义分析<button type="button" className="semantic-dismiss" aria-label="关闭语义分析" onClick={()=>setAnalysisOpen(false)}>×</button></div>
          <p>选择需要解析的 Turn，更新行为摘要、逻辑关系和 DAG。执行中的轮次按当前记录快照分析。</p>
          <div className="event-analysis-selection"><button type="button" className="semantic-button" onClick={()=>setSelectedTurns(trace.turns.map(t=>t.turn_id))}>全选</button><button type="button" className="semantic-button" onClick={()=>setSelectedTurns([])}>清空</button></div>
          <div className="event-analysis-turns">{trace.turns.map((t,index)=>{const state=live?.turns.find(s=>s.turn_id===t.turn_id);return <label key={t.turn_id}>
            <input type="checkbox" checked={selectedTurns.includes(t.turn_id)} onChange={e=>setSelectedTurns(ids=>e.target.checked?[...ids,t.turn_id]:ids.filter(id=>id!==t.turn_id))}/>
            <span><strong>Turn {index+1}</strong><span className="event-analysis-prompt">{t.prompt}</span></span>
            <small>{state?.analysis_state==='ready'?'已分析':state?.analysis_state==='running'?`分析中 ${state.percent||0}%`:state?.analysis_state==='queued'?'已排队':'未分析'}</small>
          </label>;})}</div>
          <label className="event-analysis-force"><input type="checkbox" checked={forceTurns} onChange={e=>setForceTurns(e.target.checked)}/>重新评估已分析轮次（复用未变化的事件摘要）</label>
          <div className="event-analysis-footer"><span>已选择 {selectedTurns.length} 轮</span><button type="button" className="semantic-button semantic-button-accent" disabled={submitting||!selectedTurns.length} onClick={()=>void analyzeSelected()}>{submitting?'提交中…':'开始语义分析'}</button></div>
        </section>
      </div>}
      {analysisError && <div className="shrink-0 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">{analysisError}</div>}
      <div className="semantic-layout">
        {showArtifacts && <aside className="semantic-outline event-artifact-catalog" aria-label="产物目录">
          <div className="semantic-panel-heading">产物目录 · {artifactIndex.artifacts.length}<button type="button" className="semantic-dismiss" aria-label="收起产物目录" onClick={() => setShowArtifacts(false)}>×</button></div>
          <p className="event-artifact-catalog-hint">按会话内首次交互分类编号，点击打开当前文件。</p>
          <div className="event-artifact-filters" aria-label="筛选产物类型">{[{ type: 'all', label: '全部' }, ...artifactCategories, ...(artifactIndex.artifacts.some(a => a.artifact_type === 'file') ? [{ type: 'file', label: '其他文件' }] : [])].map(category => <button type="button" key={category.type} aria-pressed={artifactFilter === category.type} onClick={() => setArtifactFilter(category.type)}>{category.type !== 'all' && <ArtifactIcon type={category.type} />}{category.label}</button>)}</div>
          <div className="event-artifact-catalog-body"><EventArtifactList links={artifactIndex.artifacts.filter(a => artifactFilter === 'all' || a.artifact_type === artifactFilter).map(artifact => ({ artifact, operations: [`${artifact.evidence_event_ids.length} 个关联事件`] }))} onOpen={id => void onOpenArtifact(id)} />
            {!artifactIndex.artifacts.some(a => artifactFilter === 'all' || a.artifact_type === artifactFilter) && <p className="event-artifact-catalog-hint">暂无这类文件的明确交互记录。</p>}
          </div>
        </aside>}
        {directoryOpen && <aside className="semantic-outline" aria-label="事件目录">
          <div className="semantic-panel-heading">事件目录<button type="button" className="semantic-dismiss" aria-label="收起事件目录" onClick={() => setDirectoryOpen(false)}>×</button></div>
          <div className="flex-1 min-h-0 overflow-auto p-2">
            {events.map((event) => <button type="button" key={event.event_id} className={`semantic-outline-item ${event.event_id === selectedId ? 'is-selected' : ''}`} onClick={() => { focus(event.event_id); setDetailsOpen(true); }}>
              <span className="semantic-outline-number" style={{ color: nodeColors(event).border }}>{String(event.sequence).padStart(2, '0')}</span>
              <span className="min-w-0"><span className="block line-clamp-2 text-xs font-semibold">{behaviors.get(event.event_id)?.title || event.title}</span><span className="block mt-1 text-[11px] text-muted">{eventTypeLabel(event.event_type)}</span></span>
            </button>)}
          </div>
        </aside>}
        <section className="semantic-canvas-panel" aria-label="执行工作流图">
          <div className="semantic-canvas-heading">
            <span className="text-xs text-muted">{legacyClassification ? '核心事件在左' : '决策、转折、结果在左'} · 实线：关键关系 · 虚线：辅助关系 · 上下连接优先 · 侧向按需简化 · 绿：逻辑 / 棕：规则 / 灰：顺序</span>
            <div className="flex gap-1">
              <button type="button" className="semantic-button semantic-button-small" disabled={!selected} onClick={() => selected && focus(selected.event_id)}>定位当前</button>
              {workflow && <button type="button" className="semantic-button semantic-button-small" onClick={() => { const first = events.find(e => isKeyEvent(importance.get(e.event_id)?.level)); if (first) focus(first.event_id); }}>关键起点</button>}
              <button type="button" className="semantic-button semantic-button-small" onClick={() => void flow?.fitView({ padding: 0.08, minZoom: 0.02, maxZoom: EXECUTION_READING_ZOOM, duration: 300 })}>查看全图</button>
            </div>
          </div>
          <div className="semantic-canvas" aria-label="执行图画布">
            <ReactFlow key={trace.session.session_id} nodes={displayNodes} edges={displayEdges} nodeTypes={executionNodeTypes} edgeTypes={executionEdgeTypes}
              onInit={setFlow} onMove={(_, viewport) => setZoom(viewport.zoom)}
              onNodeClick={(_, node) => { if (node.data.nodeKind === 'execution') { setSelectedEdgeId(null); setSelectedId(node.id); setDetailsOpen(true); } }}
              onEdgeClick={(_, edge) => { if (edge.data?.storyEdge) selectEdge(edge.id); }}
              fitView fitViewOptions={{ nodes: initialReadingNodes, padding: 0.15, minZoom: 0.18, maxZoom: EXECUTION_READING_ZOOM }}
              minZoom={0.02} maxZoom={2} nodesDraggable={false} nodesConnectable={false}
              panOnDrag zoomOnScroll zoomOnPinch zoomOnDoubleClick preventScrolling>
              <Background color="#e8e2d9" gap={24} size={1} />
              <MiniMap className="semantic-minimap" ariaLabel="执行图导航" pannable zoomable nodeColor={(node) => node.data.nodeKind === 'turnLabel' ? 'transparent' : node.data.accent || '#d6ccc0'} />
            </ReactFlow>
            <div className="semantic-zoom-controls" aria-label="执行图缩放控制">
              <button type="button" aria-label="缩小执行图" disabled={zoom <= 0.02} onClick={() => void flow?.zoomOut()}>−</button>
              <button type="button" className="semantic-zoom-value" aria-label="执行图恢复100%缩放" onClick={() => void flow?.zoomTo(1)}>{Math.round(zoom * 100)}%</button>
              <button type="button" aria-label="放大执行图" disabled={zoom >= 2} onClick={() => void flow?.zoomIn()}>+</button>
            </div>
            <div className="semantic-canvas-hint">拖动画布 · 滚轮缩放{graph.warnings.length > 0 && ` · ${graph.warnings.length} 条成环关系未绘制`}</div>
          </div>
        </section>
        {detailsOpen && <aside className="semantic-inspector" aria-label="事件详情">
          <div className="semantic-panel-heading">{selectedEdge ? '关系详情' : selected ? `事件 ${String(selected.sequence).padStart(2, '0')}` : '事件详情'}<button type="button" className="semantic-dismiss" aria-label="收起事件详情" onClick={() => setDetailsOpen(false)}>×</button></div>
          {selectedEdge ? <div className="flex-1 min-h-0 overflow-auto p-4 space-y-4">
            <p className="text-xs text-muted">原始事件间的关系。{selectedEdge.kind === 'sequence' && '记录顺序不表示业务依赖。'}</p>
            {selectedEdge.relations.map(relation => { const detail = assessedRelations.find(r => r.relation_id === relation.relation_id); return <section key={relation.relation_id} className="space-y-2 text-xs leading-5 border-b border-line pb-3">
              <h3 className="font-semibold">{relation.label || ({invokes: '发起调用', spawns: '子任务返回', prompts: '用户要求', result_feeds: '结果衔接', next_fallback: '记录顺序'} as Record<string, string>)[relation.type] || relation.type}</h3>
              <button type="button" className="block text-left text-accent" onClick={() => focus(relation.from)}>起点：{behaviors.get(relation.from)?.title || events.find(e => e.event_id === relation.from)?.title}</button>
              <button type="button" className="block text-left text-accent" onClick={() => focus(relation.to)}>终点：{behaviors.get(relation.to)?.title || events.find(e => e.event_id === relation.to)?.title}</button>
              {detail && <><p>{detail.connection_basis || detail.explanation}</p><p className="text-muted">{detail.reason}</p><p className="text-muted">置信度 {confidenceLabel(detail.confidence)} · {detail.review_status === 'accepted' ? '审查通过' : '旧版推断'}</p></>}
              <button type="button" className="semantic-button semantic-button-small" onClick={() => onEvidence(relation.from)}>查看起点原始记录</button>
            </section>; })}
          </div> : selected ? <div key={selected.event_id} className="flex-1 min-h-0 overflow-auto p-4 space-y-4">
            <div><h2 className="text-base font-semibold break-words">{behaviors.get(selected.event_id)?.title || selected.title}</h2><p className="mt-2 text-xs text-muted">{eventTypeLabel(selected.event_type)} · {executionStatusDisplay(selected.status).label}</p></div>
            <div className="space-y-2 text-xs text-muted">
              <div>执行者：{selected.actor?.id || selected.actor?.type || '—'}</div>
              <div>开始：{formatDate(selected.time?.started_at || selected.timestamp)}</div>
              <div>结束：{formatDate(selected.time?.ended_at || selected.ended_at)}</div>
              {selected.time?.duration_ms != null && <div>耗时：{selected.time.duration_ms} ms</div>}
            </div>
            <button type="button" className="semantic-button w-full justify-center" disabled={!selected.source_lines.length} onClick={() => onEvidence(selected.event_id)}>查看原始 Transcript</button>
            <EventFeedbackPanel key={selected.event_id} sessionId={trace.session.session_id} eventId={selected.event_id} sequence={selected.sequence} title={behaviors.get(selected.event_id)?.title || selected.title} />
            <p className="text-[11px] text-muted break-words">原始记录行：{selected.source_lines.join(', ') || '未记录'}</p>
            {!!artifactIndex.byEvent.get(selected.event_id)?.length && <section><h3 className="text-xs font-semibold text-muted mb-2">关联文件</h3><EventArtifactList links={artifactIndex.byEvent.get(selected.event_id)!} onOpen={id => void onOpenArtifact(id)} /></section>}
            {importance.has(selected.event_id) && <section className="rounded-xl bg-orange-50 p-3 text-xs leading-5">
              <div className="font-semibold" style={{color:eventRoleColor(importance.get(selected.event_id)?.level)}}>{importanceLabel(importance.get(selected.event_id)?.level)} · {legacyClassification ? '评级' : '分类'}置信度 {confidenceLabel(importance.get(selected.event_id)?.confidence)}</div>
              <p className="mt-1">{importance.get(selected.event_id)?.reason}</p>
              <div className="mt-1 text-muted">逻辑关联 {importance.get(selected.event_id)?.neighbor_counts?.logical || 0} · 执行关联 {importance.get(selected.event_id)?.neighbor_counts?.rules || 0}</div>
            </section>}
            {behaviors.has(selected.event_id) && <>
              <p className="text-xs text-muted">行为依据：{({requested: '用户要求', planned: '计划或调用请求', performed: '记录到的执行', reported: '报告的结果', unknown: '尚不确定'})[behaviors.get(selected.event_id)!.fact_basis]} · 摘要置信度 {confidenceLabel(behaviors.get(selected.event_id)?.confidence)}</p>
              <DetailBlock title="AI 行为摘要" value={behaviors.get(selected.event_id)?.behavior_summary} />
              <DetailBlock title="对象与输入" value={[...(behaviors.get(selected.event_id)?.objects || []), ...(behaviors.get(selected.event_id)?.inputs || [])].join('\n')} />
              <DetailBlock title="记录中的结果" value={behaviors.get(selected.event_id)?.outputs.join('\n')} />
              <DetailBlock title="不确定性与限制" value={behaviors.get(selected.event_id)?.uncertainty.join('\n')} />
              <details className="text-xs"><summary className="cursor-pointer text-muted">查看行为证据</summary>{behaviors.get(selected.event_id)?.evidence_refs.map((ref, index) => <button type="button" key={index} className="block mt-2 text-left text-accent break-words" onClick={() => onEvidence(ref.event_id)}>{ref.quote}</button>)}</details>
            </>}
            {assessedRelations.some(r => r.from === selected.event_id || r.to === selected.event_id) && <section>
              <h3 className="text-xs font-semibold text-muted mb-2">关系与审查 · 模型推断</h3>
              {assessedRelations.filter(r => r.from === selected.event_id || r.to === selected.event_id).map(relation => {
                const other = relation.from === selected.event_id ? relation.to : relation.from;
                return <div key={relation.relation_id} className="mb-2 rounded-xl border border-line p-3 text-xs leading-5">
                  <button type="button" className="text-teal-700 font-semibold text-left" onClick={() => focus(other)}>{relation.to === selected.event_id ? '来自' : '指向'}：{behaviors.get(other)?.title || other} · {relation.label}</button>
                  <p className="mt-1">{relation.explanation}</p><div className="text-muted">推断置信度 {confidenceLabel(relation.confidence)}</div>
                  <div className="text-muted">{eventRelationLabels[relation.type] || relation.type} · {relation.review_status ? ({accepted: '审查通过 · 主图采用', candidate: '证据不足 · 候选', rejected: '审查未通过'})[relation.review_status] : '旧版结果 · 未按新规范审查'}</div>
                  {relation.connection_basis && <p className="mt-1">连接依据：{relation.connection_basis}</p>}
                  {relation.reason && <p className="mt-1">审查意见：{relation.reason}</p>}
                  {relation.deterministic_issues?.map((issue, index) => <p key={index} className="text-amber-700">{issue}</p>)}
                  {!!relation.limitations?.length && <p className="text-muted">限制：{relation.limitations.join('；')}</p>}
                  <details><summary className="cursor-pointer text-muted">查看关系证据</summary>{relation.evidence_refs.map((ref, index) => <button key={index} type="button" className="block text-left mt-2 text-accent" onClick={() => onEvidence(ref.event_id)}>{ref.quote}</button>)}</details>
                  {!!relation.context_evidence_refs?.length && <details><summary className="cursor-pointer text-muted">链路补充证据</summary>{relation.context_evidence_refs.map((ref, index) => <button key={index} type="button" className="block text-left mt-2 text-accent" onClick={() => onEvidence(ref.event_id)}>{ref.quote}</button>)}</details>}
                </div>;
              })}
            </section>}
            {selected.summary && <DetailBlock title="规则事件摘要" value={selected.summary} />}
            {['tool_execution', 'command_execution'].includes(selected.event_type) ? <>
              <DetailBlock title="执行输入" value={selected.payload.input ?? selected.payload.command} />
              <DetailBlock title="执行结果" value={selected.payload.output ?? selected.payload.stdout} />
              {selected.payload.stderr && <DetailBlock title="错误输出" value={selected.payload.stderr} />}
              {selected.payload.alternate_requests && <DetailBlock title="存在差异的请求记录" value={selected.payload.alternate_requests} />}
              {selected.payload.alternate_results && <DetailBlock title="存在差异的结果记录" value={selected.payload.alternate_results} />}
            </> : <DetailBlock title="记录内容" value={selected.payload.text ?? selected.payload.result ?? selected.payload.content} />}
            <details className="text-xs"><summary className="cursor-pointer text-muted">完整事件字段</summary><DetailBlock title="Event" value={selected} /></details>
          </div> : <div className="p-4 text-sm text-muted">点击事件查看执行信息。</div>}
        </aside>}
      </div>
    </div>
  );
}

function DetailBlock({ title, value }: { title: string; value: unknown }) {
  if (value === undefined || value === null || value === '') return null;
  return <section><h3 className="mb-2 text-xs font-semibold text-muted">{title}</h3><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-stone-50 p-3 text-[11px] leading-5">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre></section>;
}

function buildExecutionGraph(trace: ObserverTrace, events: ObserverEvent[], onOpenArtifact: (artifactId: string) => Promise<void>, workflow: EventWorkflow | null, weighted: boolean, selectEdge: (id: string) => void, artifactsByEvent: Map<string, EventArtifactLink[]>, inspectArtifacts: (id: string) => void) {
  const { relations, warnings } = mergeEventRelations({ ...trace, events }, workflow);
  const layout = layoutEventTurns({ ...trace, events }, workflow, relations, weighted, new Set(artifactsByEvent.keys()));
  const behaviors = new Map(workflow?.event_summaries.map(item => [item.event_id, item]) || []);
  const importance = new Map(workflow?.event_importance.map(item => [item.event_id, item.level]) || []);
  const nodes: Node[] = [];
  for (const turn of layout.turns) {
    const promptId = turn.prompt_event_id || turn.events[0]?.event_id;
    const promptPosition = promptId ? layout.positions.get(promptId) : undefined;
    const headerWidth = Math.min(420, turn.width - 40);
    const desiredCenter = promptPosition ? promptPosition.x + layout.sizes.get(promptId!)!.width / 2 : turn.width / 2;
    const headerCenterX = Math.max(headerWidth / 2 + 20, Math.min(turn.width - headerWidth / 2 - 20, desiredCenter));
    nodes.push({ id: turn.id, type: 'turnLabel', position: { x: turn.x + headerCenterX - headerWidth / 2, y: turn.y }, zIndex: 0,
      data: { nodeKind: 'turnLabel', turnId: turn.turn_id, ordinal: turn.ordinal, title: turn.title, count: turn.events.length },
      style: { width: headerWidth, height: 44, pointerEvents: 'none' }, selectable: false, focusable: false });
    for (const event of turn.events) {
      const size = layout.sizes.get(event.event_id)!;
      const position = layout.positions.get(event.event_id)!;
      nodes.push({ id: event.event_id, type: 'execution', zIndex: 2,
        position: { x: turn.x + position.x, y: turn.y + position.y },
        data: { nodeKind: 'execution', turnId: turn.id, sequence: event.sequence, typeLabel: eventTypeLabel(event.event_type),
          title: behaviors.get(event.event_id)?.title || event.title, summary: behaviors.get(event.event_id)?.behavior_summary || event.summary,
          importance: importance.get(event.event_id), weighted, status: event.status, accent: nodeColors(event).border,
          artifacts: artifactsByEvent.get(event.event_id) || [], onOpenArtifact: (id: string) => void onOpenArtifact(id), onInspectArtifacts: () => inspectArtifacts(event.event_id) },
        style: { width: size.width, height: size.height, cursor: 'pointer' } });
    }
  }
  const routes = routeEventRelations(layout, events, relations, workflow);
  const storyEdges = relations.map(relation => ({ id: `story-${relation.relation_id}`, from: relation.from, to: relation.to,
    kind: relation.kind, label: relation.label, grouped: false, relations: [relation] }));
  const edges: Edge[] = storyEdges.map(relation => {
    const route = routes.get(relation.relations[0].relation_id)!;
    const logical = relation.kind === 'logical';
    const color = logical ? '#0f766e' : relation.kind === 'sequence' ? '#64748b' : '#78634f';
    return { id: relation.id, source: relation.from, target: relation.to, sourceHandle: route.sourceHandle, targetHandle: route.targetHandle, type: 'story', zIndex: route.primary ? 3 : 0,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 18, height: 18 },
      data: { storyEdge: relation, route, logical,
        shortLabel: route.primary ? logical ? eventRelationLabels[relation.relations[0].type] || '逻辑联系' : '执行衔接' : undefined,
        fullLabel: relation.label || '执行连接', onSelect: () => selectEdge(relation.id) },
      style: { stroke: color, strokeWidth: route.primary ? 2.6 : 1.7, opacity: 1,
        strokeDasharray: route.primary ? undefined : '6 4' },
    };
  });
  return { nodes, edges, story: { edges: storyEdges }, turns: layout.turns, warnings };
}

function eventTypeLabel(type: string): string {
  return ({ user_prompt: '用户输入', model_response: '模型响应', tool_execution: '工具执行', command_execution: '命令执行', subagent_result: '子任务结果', control_event: '控制事件', assistant_message: '模型消息' } as Record<string, string>)[type] || type;
}
function executionStatusDisplay(status: string): { label: string; color: string } {
  if (status === 'conflicting') return { label: '记录冲突', color: '#b45309' };
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

function importanceLabel(level?: EventImportanceLevel) { return eventRoleLabel(level); }
function confidenceLabel(value?: string) { return ({high: '高', medium: '中', low: '低'} as Record<string, string>)[value || ''] || '未知'; }
