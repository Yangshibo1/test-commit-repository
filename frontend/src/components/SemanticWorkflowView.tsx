import { memo, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  BaseEdge,
  Edge,
  EdgeProps,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  MiniMap,
  Node,
  NodeProps,
  Position,
  ReactFlowInstance,
  useViewport,
} from 'reactflow';
import 'reactflow/dist/style.css';
import './SemanticWorkflowView.css';
import { ObserverTrace } from '../types/observer';
import { SemanticMetrics, SemanticProgress, SemanticWorkflow, SemanticSwimlanes, SemanticSwimlaneProgress } from '../types/semantic';
import { projectSemanticSwimlanes, semanticLanes, swimlaneEdgeLabel, validateSemanticSwimlanes } from '../utils/semanticSwimlanes';
import { attachRoutePorts } from '../utils/eventRouting';
import SemanticWorkflowInspector from './SemanticWorkflowInspector';
import type { SemanticInspectorTab } from './SemanticWorkflowInspector';

interface SemanticWorkflowViewProps {
  trace: ObserverTrace;
  workflow: SemanticWorkflow | null;
  loading: boolean;
  progress: SemanticProgress | null;
  onGenerate: (annotationGuidance: string, resumeInference?: string | null) => Promise<void>;
  onEvidence: (eventId: string) => void;
  onOpenArtifact: (artifactId: string) => Promise<void>;
}

const SEMANTIC_NODE_WIDTH = 300;
const SEMANTIC_NODE_HEIGHT = 116;
const READING_ZOOM = 0.9;

interface SemanticGraphNodeData {
  nodeKind: 'semantic';
  sequence: number;
  activity: string;
  activityLabel: string;
  title: string;
  eventCount: number;
  toolCount: number;
  commandCount: number;
  outcomeCount: number;
  artifactCount: number;
  errorCount: number;
  reviewStatus: string;
  origin: string;
  accent: string;
  groupId: string;
  nodeIds: string[];
  stageCount: number;
  rangeLabel: string;
  summary: string;
  isGroup: boolean;
  expanded: boolean;
  onToggle?: () => void;
  artifacts: Array<{id:string;name:string;exists:boolean}>;
  onArtifact?: (id:string) => void;
}

const SemanticGraphNode = memo(({ data, selected }: NodeProps<SemanticGraphNodeData>) => {
  const { zoom } = useViewport();
  const overview = zoom < 0.6;
  const compact = zoom >= 0.6 && zoom < 0.8;
  const statusLabel = data.reviewStatus === 'accepted'
    ? '已确认'
    : data.reviewStatus === 'corrected'
    ? '已修订'
    : data.origin === 'user_validated'
    ? '已验证'
    : '待复核';
  const statusColor = data.reviewStatus === 'accepted' || data.origin === 'user_validated'
    ? '#15803d'
    : data.reviewStatus === 'corrected'
    ? '#7c3aed'
    : '#a8a29e';

  return (
    <div
      className={`relative h-full w-full overflow-hidden rounded-2xl border bg-[#fffdfb] font-sans transition-[box-shadow,border-color] duration-200 ${
        selected ? 'border-accent shadow-[0_16px_34px_rgba(217,119,69,0.24)]' : 'border-[#e7ded3] shadow-[0_8px_22px_rgba(76,55,32,0.10)]'
      }`}
      style={{ borderLeftWidth: 4, borderLeftColor: data.accent }}
      title={`${String(data.sequence).padStart(2, '0')} · ${data.activityLabel} · ${data.title}`}
    >
      {overview ? (
        <div className="flex h-full items-center gap-4 px-5">
          <span className="text-3xl font-semibold tabular-nums" style={{ color: data.accent }}>
            {data.rangeLabel}
          </span>
          <div className="min-w-0">
            <div className="text-base font-semibold text-[#302a25] line-clamp-2">{data.title}</div>
            <div className="mt-1 text-sm text-muted">{data.activityLabel}</div>
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-col px-4 py-3">
          <div className="flex shrink-0 items-center gap-2">
            <span
              className="inline-flex h-6 min-w-8 items-center justify-center rounded-md px-1.5 text-xs font-bold tabular-nums text-white"
              style={{ backgroundColor: data.accent }}
            >
              {data.rangeLabel}
            </span>
            <span className="min-w-0 truncate rounded-full bg-stone-100 px-2 py-1 text-[11px] font-semibold text-[#625a52]">
              {data.activityLabel}
            </span>
            <span className="ml-auto flex shrink-0 items-center gap-1.5 text-[10px] font-medium text-[#81776e]">
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusColor }} />
              {statusLabel}
            </span>
          </div>
          <div className="mt-2 overflow-hidden text-[15px] font-semibold leading-5 text-[#29241f] line-clamp-2">
            {data.title}
          </div>
          {!compact && data.isGroup && <p className="mt-1 line-clamp-2 text-[11px] text-muted leading-4">{data.summary}</p>}
          {!compact && (
            <div className="mt-auto flex min-h-4 shrink-0 items-center gap-3 overflow-hidden text-[11px] font-medium text-[#7a7067]">
              <span className="whitespace-nowrap">{data.stageCount} 个阶段 · {data.eventCount} 条记录</span>
              {data.toolCount > 0 && <span className="whitespace-nowrap">{data.toolCount} 次工具调用</span>}
              {data.commandCount > 0 && <span className="whitespace-nowrap">{data.commandCount} 条命令</span>}
              {data.artifactCount > 0 && <span className="whitespace-nowrap">{data.artifactCount} 个文件</span>}
              {data.errorCount > 0 && <span className="whitespace-nowrap text-red-700">{data.errorCount} 个异常</span>}
            </div>
          )}
        </div>
      )}

      {data.isGroup && data.stageCount > 1 && <button type="button" className="semantic-aggregate-toggle nodrag nopan" onClick={event=>{event.stopPropagation();data.onToggle?.();}}>{data.expanded?'收起阶段':'展开阶段'}</button>}
      {data.artifacts.length > 0 && zoom >= .6 && <div className="semantic-artifact-chips">{data.artifacts.slice(0,2).map(a=><button key={a.id} type="button" disabled={!a.exists} className="nodrag nopan" title={a.name} onClick={event=>{event.stopPropagation();data.onArtifact?.(a.id);}}>↗ {a.name}</button>)}</div>}

      <Handle
        type="target"
        position={Position.Top}
        id="main-in"
        className="!h-1.5 !w-1.5 !border-0 !opacity-0"
        style={{ backgroundColor: data.accent }}
      />
      {([Position.Top,Position.Bottom,Position.Left,Position.Right] as const).map(side=><Handle key={`in-${side}`} type="target" position={side} id={`in-${side}`} className="!opacity-0" />)}
      {([Position.Top,Position.Bottom,Position.Left,Position.Right] as const).map(side=><Handle key={`out-${side}`} type="source" position={side} id={`out-${side}`} className="!opacity-0" />)}
      <Handle
        type="source"
        position={Position.Bottom}
        id="main-out"
        className="!h-1.5 !w-1.5 !border-0 !opacity-0"
        style={{ backgroundColor: data.accent }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="artifact-out"
        className="!h-1.5 !w-1.5 !border-0 !opacity-0"
        style={{ top: 76, backgroundColor: '#0f766e' }}
      />
    </div>
  );
});

SemanticGraphNode.displayName = 'SemanticGraphNode';

const SwimlaneHeading = memo(({data}:NodeProps)=><div className="semantic-lane-heading" style={{color:data.color}}><strong>{data.title}</strong><span>{data.count} 个语义块</span><p>{data.description}</p></div>);
const SwimlaneBackdrop = memo(({data}:NodeProps)=><div className="semantic-lane-backdrop" style={{background:data.tint,borderColor:data.color+'20'}} />);
const SemanticSwimlaneEdge = memo((props:EdgeProps)=>{
  const points=attachRoutePorts(props.data.points,{x:props.sourceX,y:props.sourceY},{x:props.targetX,y:props.targetY});
  const path=points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ');
  const segments=points.slice(1).map((p,i)=>({a:points[i],b:p,length:Math.abs(p.x-points[i].x)+Math.abs(p.y-points[i].y)})).sort((a,b)=>b.length-a.length);
  const longest=segments[0],labelPoint=longest?{x:(longest.a.x+longest.b.x)/2,y:(longest.a.y+longest.b.y)/2}:{x:props.sourceX,y:props.sourceY};
  return <><BaseEdge path={path} markerEnd={props.markerEnd} style={props.style}/>{props.data.type!=='NEXT'&&<EdgeLabelRenderer><div className="semantic-swimlane-edge-label" style={{transform:`translate(-50%, -50%) translate(${labelPoint.x}px,${labelPoint.y}px)`}} title={props.data.description}>{swimlaneEdgeLabel(props.data.type)}</div></EdgeLabelRenderer>}</>;
});
const semanticNodeTypes = { semantic: SemanticGraphNode, laneHeading:SwimlaneHeading, laneBackdrop:SwimlaneBackdrop };
const semanticEdgeTypes = {swimlane:SemanticSwimlaneEdge};

export default function SemanticWorkflowView({
  trace,
  workflow,
  loading,
  progress,
  onGenerate,
  onEvidence,
  onOpenArtifact,
}: SemanticWorkflowViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<SemanticInspectorTab>('overview');
  const [aggregation, setAggregation] = useState<SemanticSwimlanes|null>(null);
  const [aggregateProgress, setAggregateProgress] = useState<SemanticSwimlaneProgress|null>(null);
  const [aggregateError, setAggregateError] = useState<string|null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const aggregateEndpoint=`/api/observations/${encodeURIComponent(trace.session.session_id)}/semantic/swimlanes`;
  const aggregateBusy=['scheduled','running'].includes(aggregateProgress?.status||'');
  const [zoom, setZoom] = useState(READING_ZOOM);
  const [annotationGuidance, setAnnotationGuidance] = useState('保持阶段级摘要：标题简短，目标一到两句，行为摘要两到三句，结果保留关键数字与限制。');

  useEffect(() => {
    setSelectedNodeId((current) => (
      current && workflow?.semantic_nodes.some((node) => node.node_id === current)
        ? current
        : workflow?.semantic_nodes[0]?.node_id || null
    ));
  }, [workflow?.inference_run.inference_id, workflow?.review.review_event_count]);

  useEffect(() => {
    const savedGuidance = progress?.annotation_guidance
      || workflow?.inference_run.annotation_guidance;
    if (savedGuidance) setAnnotationGuidance(savedGuidance);
  }, [
    progress?.inference_id,
    progress?.annotation_guidance,
    workflow?.inference_run.inference_id,
    workflow?.inference_run.annotation_guidance,
  ]);

  const selectedNode = workflow?.semantic_nodes.find((node) => node.node_id === selectedNodeId) || null;
  const currentAggregation=useMemo(()=>{
    if(!workflow||!aggregation)return null;
    try{return validateSemanticSwimlanes(aggregation,workflow);}catch{return null;}
  },[workflow,aggregation]);
  const graph = useMemo(
    () => buildSemanticGraph(workflow, trace, currentAggregation, expandedGroups),
    [workflow, trace, currentAggregation, expandedGroups],
  );
  const selectedGroup=graph.groups.find(group=>group.node_ids.includes(selectedNodeId||''));
  const displayNodes=useMemo(()=>graph.nodes.map(node=>node.type!=='semantic'?node:{...node,selected:graph.nodeForStageId.get(selectedNodeId||'')===node.id,data:{...node.data,
    onToggle:()=>setExpandedGroups(current=>{const next=new Set(current);if(next.has(node.data.groupId))next.delete(node.data.groupId);else next.add(node.data.groupId);return next;}),
    onArtifact:(id:string)=>void onOpenArtifact(id),
  }}),[graph,selectedNodeId,onOpenArtifact]);

  useEffect(()=>{
    let active=true;setAggregation(null);setAggregateError(null);setExpandedGroups(new Set());setAggregateProgress(null);
    if(workflow)void Promise.all([fetch(aggregateEndpoint),fetch(aggregateEndpoint+'/progress')]).then(async([result,state])=>{
      const value=result.ok?await result.json():null;const update=state.ok?await state.json():null;
      if(!active)return;
      if(value)setAggregation(validateSemanticSwimlanes(value,workflow));
      if(update)setAggregateProgress(update);
    }).catch(error=>{if(active)setAggregateError(String(error));});
    return()=>{active=false;};
  },[aggregateEndpoint,workflow]);
  useEffect(()=>{
    if(!aggregateBusy||!workflow)return;
    let active=true;
    const timer=window.setInterval(()=>{void fetch(aggregateEndpoint+'/progress').then(r=>r.json()).then(async(state:SemanticSwimlaneProgress)=>{
      if(!active)return;setAggregateProgress(state);
      if(state.status==='ready'){
        const result=await fetch(aggregateEndpoint);if(!result.ok)throw new Error('原阶段已更新，请重新聚合');
        const value=await result.json();if(active)setAggregation(validateSemanticSwimlanes(value,workflow));
      }
      if(state.error&&active)setAggregateError(state.error);
    }).catch(error=>{if(active){setAggregateError(String(error));setAggregateProgress({status:'partial',message:'聚合读取失败，可重试'});}});},2000);
    return()=>{active=false;window.clearInterval(timer);};
  },[aggregateBusy,aggregateEndpoint,workflow]);
  const generateAggregation=async()=>{
    setAggregateError(null);setAggregateProgress({status:'scheduled',message:'等待语义聚合'});
    try{const result=await fetch(aggregateEndpoint+'/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force:!!aggregation,resume:true})});const value=await result.json();if(!result.ok)throw new Error(value.detail||'聚合失败');setAggregateProgress(value);}
    catch(error){setAggregateError(String(error));setAggregateProgress({status:'partial',message:'聚合未完成，可重试'});}
  };
  const sourceEventTypeCounts = useMemo(() => trace.events.reduce<Record<string, number>>(
    (counts, event) => ({ ...counts, [event.event_type]: (counts[event.event_type] || 0) + 1 }),
    {},
  ), [trace.events]);

  const focusNode = (nodeId: string, zoom = READING_ZOOM) => {
    setSelectedNodeId(nodeId);
    const target = graph.nodes.find((node) => node.id === graph.nodeForStageId.get(nodeId) && node.data?.nodeKind === 'semantic');
    if (!flowInstance || !target) return;
    void flowInstance.setCenter(
      target.position.x + SEMANTIC_NODE_WIDTH / 2,
      target.position.y + Number(target.style?.height||SEMANTIC_NODE_HEIGHT) / 2,
      { zoom, duration: 320 },
    );
  };

  if (!workflow) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-xl rounded-3xl border border-line bg-white/80 p-8 text-center shadow-lg">
          <div className="text-accent text-xs font-medium">从记录到工作流</div>
          <h2 className="font-semibold text-2xl mt-3">整理这次分析的过程</h2>
          <p className="text-muted text-sm leading-6 mt-3">
            将会话记录整理成清晰的分析阶段，连接每个阶段的目标、结果与原始证据。
          </p>
          <label className="block text-left text-xs text-muted mt-6">
            阶段摘要要求
            <textarea
              value={annotationGuidance}
              onChange={(event) => setAnnotationGuidance(event.target.value)}
              maxLength={1000}
              rows={4}
              placeholder="例如：每个阶段保留一个目标、两句摘要和三条关键结果。"
              className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-ink text-sm resize-none"
            />
            <span className="block mt-1 text-[11px]">控制摘要的详略，保留原始记录与证据引用。</span>
          </label>
          <div className="flex items-center justify-center mt-4">
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(annotationGuidance)}
              className="px-5 py-2.5 rounded-full bg-accent text-white text-sm disabled:opacity-50"
            >
              {loading ? '正在整理…' : '生成分析工作流'}
            </button>
          </div>
          {(loading || progress) && <SemanticProgressBar progress={progress} />}
          {progress?.status === 'partial' && progress.retryable && progress.inference_id && (
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(annotationGuidance, progress.inference_id)}
              className="mt-4 px-5 py-2.5 rounded-full bg-accent text-white text-sm disabled:opacity-50"
            >
              继续未完成分析
            </button>
          )}
        </div>
      </div>
    );
  }

  const running = loading || ['running', 'scheduled', 'retrying', 'partial'].includes(progress?.status || '');
  const eventCount = workflow.source_events?.event_count || workflow.validation.source_event_count || trace.events.length;
  const runtime = running && progress ? progress : workflow.inference_run;

  return (
    <div className="semantic-workspace semantic-swimlane-workspace">
      <div className="semantic-toolbar">
        <div className="flex min-w-0 items-center gap-3">
          <span className="semantic-workflow-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <rect x="8" y="2" width="8" height="5" rx="1.5" /><rect x="2" y="17" width="8" height="5" rx="1.5" /><rect x="14" y="17" width="8" height="5" rx="1.5" /><path d="M12 7v5M6 17v-5h12v5" />
            </svg>
          </span>
          <div>
            <div className="text-sm font-semibold text-ink">四泳道语义工作流</div>
            <div className="text-xs text-muted mt-0.5">{graph.groups.length} 个语义块 · {workflow.semantic_nodes.length} 个原阶段 · {eventCount} 条记录</div>
          </div>
        </div>
        <div className="semantic-toolbar-metrics">
          <SemanticMetric label="工具调用" value={workflow.source_events?.event_type_counts?.tool_execution ?? sourceEventTypeCounts.tool_execution ?? 0} />
          <SemanticMetric label="命令执行" value={workflow.source_events?.event_type_counts?.command_execution ?? sourceEventTypeCounts.command_execution ?? 0} />
          <SemanticMetric label="子任务" value={workflow.source_events?.event_type_counts?.subagent_result ?? sourceEventTypeCounts.subagent_result ?? 0} />
        </div>
        <div className="semantic-toolbar-actions">
          <button type="button" className="semantic-button semantic-button-accent" disabled={aggregateBusy||loading||['scheduled','running','retrying'].includes(progress?.status||'')} onClick={()=>void generateAggregation()}>{aggregateBusy?'正在聚合…':aggregation?'重新聚合语义':'聚合语义'}</button>
          <button type="button" className="semantic-button" aria-pressed={outlineOpen} onClick={() => setOutlineOpen(!outlineOpen)}>阶段目录</button>
          <button type="button" className="semantic-button" aria-pressed={inspectorOpen} onClick={() => setInspectorOpen(!inspectorOpen)}>阶段详情</button>
          <button type="button" className="semantic-button semantic-button-accent" aria-expanded={settingsOpen} aria-controls="semantic-analysis-settings" onClick={() => setSettingsOpen(!settingsOpen)}>分析设置{running && <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current" />}</button>
        </div>
      </div>
      <div className="semantic-aggregation-status" aria-label="语义聚合状态">
        <span>{aggregation?'AI 按共同目标聚合 · 可展开原阶段':'按现有阶段归类 · 聚合语义后精简'}</span>
        <span>泳道内从上到下 · 跨列推进与回访保留原顺序</span>
        {aggregateBusy&&<span>{aggregateProgress?.message}</span>}
        {aggregation&&<span>{aggregation.inference_run.model} · {aggregation.inference_run.call_count} 次调用 · {Math.round(aggregation.inference_run.elapsed_seconds)} 秒</span>}
      </div>
      {aggregateError&&<div className="semantic-aggregation-error">{aggregateError}</div>}

      <div className="semantic-layout">
        {outlineOpen && (
          <aside className="semantic-outline" aria-label="阶段目录">
            <div className="semantic-panel-heading">
              <span>语义块目录 <span className="ml-1 text-muted font-normal">{graph.groups.length}</span></span>
              <button type="button" className="semantic-dismiss" aria-label="收起阶段目录" onClick={() => setOutlineOpen(false)}>×</button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-2 space-y-1">
              {graph.groups.map((group,index) => (
                <button key={group.group_id} type="button" aria-current={selectedGroup?.group_id===group.group_id ? 'step' : undefined} className={`semantic-outline-item ${selectedGroup?.group_id===group.group_id ? 'is-selected' : ''}`} onClick={() => { focusNode(group.node_ids[0]); setInspectorTab('overview'); setInspectorOpen(true); }}>
                  <span className="semantic-outline-number" style={{ color: semanticLanes.find(l=>l.id===group.lane)?.color }}>{String(index+1).padStart(2,'0')}</span>
                  <span className="min-w-0">
                    <span className="block font-semibold text-[13px] leading-5 line-clamp-2">{group.title}</span>
                    <span className="mt-1 block text-[11px] text-muted">{semanticLanes.find(l=>l.id===group.lane)?.title} · {group.node_ids.length} 个原阶段</span>
                  </span>
                </button>
              ))}
            </div>
          </aside>
        )}

        <section className="semantic-canvas-panel" aria-label="工作流图">
          <div className="semantic-canvas-heading">
            <div className="flex items-center gap-2 min-w-0">
              <span className="h-2 w-2 shrink-0 rounded-full bg-accent" />
              <span className="text-xs font-medium text-[#64594f]">输入 → 规划 → 执行 → 修改 · 修改后可返回执行</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button type="button" disabled={!selectedNodeId} onClick={() => selectedNodeId && focusNode(selectedNodeId)} className="semantic-button semantic-button-small">定位当前</button>
              <button type="button" onClick={()=>void flowInstance?.fitView({nodes:graph.initialNodes,padding:.04,minZoom:.1,maxZoom:READING_ZOOM,duration:250})} className="semantic-button semantic-button-small">泳道总览</button>
              <button type="button" onClick={() => void flowInstance?.fitView({ padding: 0.12, minZoom: 0.02, maxZoom: 1, duration: 250 })} className="semantic-button semantic-button-small">查看全图</button>
            </div>
          </div>
          <div className="semantic-canvas" aria-label="工作流画布">
            <ReactFlow
              key={`${workflow.inference_run.inference_id}-${aggregation?.source_hash||'existing'}-swimlanes`}
              nodes={displayNodes}
              edges={graph.edges}
              nodeTypes={semanticNodeTypes}
              edgeTypes={semanticEdgeTypes}
              defaultViewport={{ x: 80, y: 12, zoom: READING_ZOOM }}
              fitView
              fitViewOptions={{ nodes: graph.initialNodes, padding: 0.04, minZoom: 0.1, maxZoom: READING_ZOOM }}
              minZoom={0.02}
              maxZoom={2}
              nodesDraggable={false}
              nodesConnectable={false}
              panOnDrag
              zoomOnScroll
              zoomOnPinch
              zoomOnDoubleClick
              preventScrolling
              onInit={setFlowInstance}
              onMove={(_, viewport) => setZoom(viewport.zoom)}
              onNodeClick={(_, node) => {
                if (node.data?.nodeKind === 'semantic') {
                  setSelectedNodeId(node.data.nodeIds[0]);
                  setInspectorTab(node.data.isGroup ? 'overview' : 'stages');
                  setInspectorOpen(true);
                }
              }}
            >
              <Background color="#ddd4ca" gap={24} size={1} />
              <MiniMap nodeColor={(node) => node.data?.accent || '#b9c7c2'} pannable zoomable ariaLabel="工作流导航" className="semantic-minimap" />
            </ReactFlow>
            <div className="semantic-zoom-controls" aria-label="画布缩放控制">
              <button type="button" aria-label="缩小画布" title="缩小" disabled={zoom <= 0.02} onClick={() => void flowInstance?.zoomOut({ duration: 150 })}>−</button>
              <button type="button" className="semantic-zoom-value" aria-label="恢复100%缩放" title="恢复 100%" onClick={() => void flowInstance?.zoomTo(1, { duration: 150 })}>{Math.round(zoom * 100)}%</button>
              <button type="button" aria-label="放大画布" title="放大" disabled={zoom >= 2} onClick={() => void flowInstance?.zoomIn({ duration: 150 })}>+</button>
            </div>
            <div className="semantic-canvas-hint">拖动与缩放 · 虚线为顺序 · 彩色线为已有语义引用</div>
          </div>
          {running && <div className="semantic-running"><SemanticProgressBar progress={progress} compact /></div>}
        </section>

        {inspectorOpen && (
          <aside className="semantic-inspector" aria-label="阶段详情">
            {selectedGroup && selectedNode ? (
              <SemanticWorkflowInspector key={selectedGroup.group_id} group={selectedGroup} node={selectedNode}
                trace={trace} workflow={workflow} aggregated={!!currentAggregation} tab={inspectorTab}
                onTabChange={setInspectorTab} onSelect={setSelectedNodeId} onEvidence={onEvidence}
                onClose={() => setInspectorOpen(false)} />
            ) : <><div className="semantic-panel-heading">阶段详情<button type="button" className="semantic-dismiss" aria-label="收起阶段详情" onClick={() => setInspectorOpen(false)}>×</button></div><div className="semantic-detail-body">点击语义块，查看结果与证据。</div></>}

          </aside>
        )}

        {settingsOpen && (
          <aside id="semantic-analysis-settings" className="semantic-settings" aria-label="分析设置">
            <div className="semantic-panel-heading">
              <span>分析设置</span>
              <button type="button" className="semantic-dismiss" aria-label="关闭分析设置" onClick={() => setSettingsOpen(false)}>×</button>
            </div>
            <div className="min-h-0 overflow-auto p-4">
              <p className="text-xs leading-5 text-muted">调整阶段摘要的详略，重新整理本次会话。</p>
              <label className="mt-4 block text-xs font-medium text-ink">
                阶段摘要要求
                <textarea value={annotationGuidance} onChange={(event) => setAnnotationGuidance(event.target.value)} maxLength={1000} rows={4} className="semantic-guidance" />
              </label>
              <button type="button" disabled={loading} onClick={() => void onGenerate(annotationGuidance)} className="semantic-generate-button mt-3">{loading ? '正在分析…' : '重新生成工作流'}</button>
              {progress?.status === 'partial' && progress.retryable && progress.inference_id && (
                <button type="button" disabled={loading} onClick={() => void onGenerate(annotationGuidance, progress.inference_id)} className="semantic-button mt-2 w-full justify-center">继续未完成分析</button>
              )}
              <div className="mt-5 border-t border-line pt-4">
                <h3 className="text-xs font-semibold text-ink">{running ? '本次分析' : '最近一次分析'}</h3>
                <SemanticRuntime metrics={runtime} progress={running ? progress || undefined : undefined} />
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function buildSemanticGraph(
  workflow: SemanticWorkflow | null,
  trace: ObserverTrace,
  aggregation: SemanticSwimlanes | null,
  expanded: Set<string>,
) {
  if (!workflow) return {nodes:[] as Node[],edges:[] as Edge[],groups:[],nodeForStageId:new Map<string,string>(),initialNodes:[] as Node[]};
  const projection=projectSemanticSwimlanes(workflow,aggregation,expanded);
  const originals=new Map(workflow.semantic_nodes.map(node=>[node.node_id,node]));
  const events=new Map(trace.events.map(event=>[event.event_id,event]));
  const nodes:Node[]=projection.units.map(unit=>{
    const members=unit.node_ids.map(id=>originals.get(id)!);
    const eventIds=new Set(members.flatMap(node=>node.event_ids));
    const artifacts=(trace.artifacts||[]).filter(artifact=>artifact.operations.some(op=>eventIds.has(op.event_id)));
    const lane=semanticLanes.find(lane=>lane.id===unit.group.lane)!;
    const types:Record<string,number>={};eventIds.forEach(id=>{const type=events.get(id)?.event_type;if(type)types[type]=(types[type]||0)+1;});
    return {id:unit.id,type:'semantic',position:{x:unit.x,y:unit.y},zIndex:2,
      data:{nodeKind:'semantic',sequence:members[0].sequence,activity:lane.id,activityLabel:lane.title,
        title:unit.member?.title||unit.group.title,summary:unit.member?.summary.value||unit.group.summary,
        groupId:unit.group.group_id,nodeIds:unit.node_ids,stageCount:members.length,isGroup:!unit.member,expanded:expanded.has(unit.group.group_id),
        rangeLabel:members.length>1?`${members[0].sequence}–${members[members.length-1].sequence}`:String(members[0].sequence).padStart(2,'0'),
        eventCount:eventIds.size,toolCount:types.tool_execution||0,commandCount:types.command_execution||0,outcomeCount:members.reduce((n,m)=>n+m.outcome_claims.length,0),
        artifactCount:artifacts.length,errorCount:members.reduce((n,m)=>n+m.errors.length,0),
        reviewStatus:aggregation&&!unit.member?'unreviewed':members.every(m=>m.review_status==='accepted')?'accepted':members.length>1?'unreviewed':members[0].review_status,
        origin:aggregation&&!unit.member?'inferred':members[0].origin,accent:lane.color,
        artifacts:artifacts.map(a=>({id:a.artifact_id,name:a.name,exists:a.exists})),
      },style:{width:unit.width,height:unit.height},
    };
  });
  const headings:Node[]=projection.lanes.map(lane=>({id:`lane-heading-${lane.id}`,type:'laneHeading',position:{x:lane.x+16,y:24},data:{...lane},style:{width:lane.width-32,height:62},zIndex:3,selectable:false,draggable:false,focusable:false}));
  const backdrops:Node[]=projection.lanes.map(lane=>({id:`lane-backdrop-${lane.id}`,type:'laneBackdrop',position:{x:lane.x,y:16},data:{...lane},style:{width:lane.width,height:projection.height-16},zIndex:-10,selectable:false,draggable:false,focusable:false}));
  const edges:Edge[]=projection.edges.map(link=>({id:link.id,source:link.from,target:link.to,type:'swimlane',sourceHandle:link.sourceHandle,targetHandle:link.targetHandle,
    data:{...link,description:`${swimlaneEdgeLabel(link.type)} · 保留 ${link.relation_ids.length} 条原关系 · ${link.origin} · 置信度 ${link.confidence}`},
    markerEnd:{type:MarkerType.ArrowClosed,color:link.type==='NEXT'?'#a8a29e':'#7c3aed',width:14,height:14},zIndex:1,
    style:{stroke:link.type==='NEXT'?'#a8a29e':'#7c3aed',strokeWidth:link.type==='NEXT'?1.4:1.9,strokeDasharray:link.type==='NEXT'?'5 5':undefined,strokeLinejoin:'round'},
  }));
  return {...projection,nodes:[...backdrops,...headings,...nodes],edges,initialNodes:[...headings,...nodes.filter(n=>n.position.y<340)]};
}

function SemanticMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted">{label}</span>
      <span className="font-semibold tabular-nums text-ink">{value}</span>
    </div>
  );
}

function SemanticProgressBar({
  progress,
  compact = false,
}: {
  progress: SemanticProgress | null;
  compact?: boolean;
}) {
  const percent = Math.max(0, Math.min(progress?.percent ?? 0, 100));
  if (progress?.status === 'idle') return <SemanticRuntime metrics={progress} />;
  return (
    <div className={compact ? 'mt-2' : 'mt-6 text-left'}>
      <div className="flex items-center justify-between gap-3 text-[10px] font-mono text-muted mb-1">
        <span>{progress?.message?.replace(/Episode/g, '阶段').replace('Semantic Workflow', '分析工作流') || '准备整理工作流…'}</span>
        <span>{percent}%</span>
      </div>
      <div className="h-2 rounded-full bg-stone-200 overflow-hidden">
        <div
          className="h-full bg-accent transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      {!compact && progress?.current && progress?.total && (
        <div className="text-[10px] text-muted font-mono mt-1">
          阶段 {progress.current}/{progress.total}
        </div>
      )}
      {!compact && progress?.status === 'partial' && (
        <div className="text-[10px] text-orange-700 mt-2">
          已完成 {progress.completed_episode_count ?? 0}/{progress.total ?? '—'} 个阶段；
          当前结果已保存，可从检查点继续。
        </div>
      )}
      {progress && !compact && <SemanticRuntime metrics={progress} progress={progress} />}
      {progress && compact && <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted">
        <span>{progress.model || '准备分析'}</span>
        <span>{progress.completed_episode_count ?? 0}/{progress.total ?? '—'} 个阶段</span>
        <span>{progress.call_count ?? 0} 次调用</span>
      </div>}
    </div>
  );
}

const STAGE_LABELS: Record<string, string> = {
  boundaries: '阶段边界', semantic_annotation: '语义标注',
  relations: '关系提取', validation: '结果校验',
};

function duration(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  return value >= 60 ? `${Math.floor(value / 60)}分${value % 60}秒` : `${value}秒`;
}

function SemanticRuntime({ metrics, progress }: {
  metrics: SemanticMetrics;
  progress?: SemanticProgress;
}) {
  const [now, setNow] = useState(Date.now());
  const active = !!progress && ['running', 'retrying'].includes(progress.status);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const updated = progress?.updated_at ? Date.parse(progress.updated_at) : NaN;
  const extra = active && Number.isFinite(updated) ? Math.max(0, (now - updated) / 1000) : 0;
  const timings = metrics.stage_timings || [];
  const currentStage = progress?.stage === 'retrying'
    ? timings[timings.length - 1]?.stage : progress?.stage;
  return (
    <div className="mt-2 rounded-xl bg-[#faf8f5] px-3 py-3 text-xs leading-6 text-muted" aria-label="语义处理运行指标">
      <div className="break-all text-ink">模型：{metrics.model || '规则模式'}</div>
      {!!metrics.annotation_concurrency && <div>标注并发：{metrics.annotation_concurrency} 路</div>}
      {metrics.elapsed_seconds !== undefined && (
        <div className="mt-1">总耗时 {duration(metrics.elapsed_seconds + extra)} · 调用 {metrics.call_count ?? 0} 次</div>
      )}
      {metrics.request_count !== undefined && metrics.request_count !== metrics.call_count && (
        <div>实际请求 {metrics.request_count} 次（含格式调整与重试）</div>
      )}
      {timings.length > 0 && (
        <table className="w-full mt-1.5 text-left">
          <thead><tr><th className="font-normal text-[11px]">阶段</th><th className="font-normal text-right text-[11px]">耗时 / 调用</th></tr></thead>
          <tbody>{timings.map((item) => (
            <tr key={item.stage}>
              <td>{STAGE_LABELS[item.stage] || item.stage}</td>
              <td className="text-right">{duration(item.elapsed_seconds + (item.stage === currentStage ? extra : 0))} / {item.call_count}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
