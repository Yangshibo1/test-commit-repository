import { memo, useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Handle,
  MiniMap,
  Node,
  NodeProps,
  Position,
  ReactFlowInstance,
  useViewport,
} from 'reactflow';
import dagre from 'dagre';
import { ObserverTrace } from '../types/observer';
import { SemanticNode, SemanticProgress, SemanticWorkflow } from '../types/semantic';

interface SemanticWorkflowViewProps {
  trace: ObserverTrace;
  workflow: SemanticWorkflow | null;
  loading: boolean;
  progress: SemanticProgress | null;
  onGenerate: (annotationGuidance: string, resumeInference?: string | null) => Promise<void>;
  onEvidence: (eventId: string) => void;
  onOpenArtifact: (artifactId: string) => Promise<void>;
}

const SEMANTIC_NODE_WIDTH = 276;
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
            {String(data.sequence).padStart(2, '0')}
          </span>
          <div className="min-w-0">
            <div className="text-base font-semibold text-[#302a25]">{data.activityLabel}</div>
            <div className="mt-1 h-1.5 w-16 rounded-full" style={{ backgroundColor: data.accent }} />
          </div>
        </div>
      ) : (
        <div className="flex h-full flex-col px-4 py-3">
          <div className="flex shrink-0 items-center gap-2">
            <span
              className="inline-flex h-6 min-w-8 items-center justify-center rounded-md px-1.5 text-xs font-bold tabular-nums text-white"
              style={{ backgroundColor: data.accent }}
            >
              {String(data.sequence).padStart(2, '0')}
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
          {!compact && (
            <div className="mt-auto flex min-h-4 shrink-0 items-center gap-3 overflow-hidden text-[11px] font-medium text-[#7a7067]">
              <span className="whitespace-nowrap">{data.eventCount} Events</span>
              {data.toolCount > 0 && <span className="whitespace-nowrap">{data.toolCount} Tools</span>}
              {data.commandCount > 0 && <span className="whitespace-nowrap">{data.commandCount} Commands</span>}
              {data.artifactCount > 0 && <span className="whitespace-nowrap">{data.artifactCount} 个文件</span>}
              {data.errorCount > 0 && <span className="whitespace-nowrap text-red-700">{data.errorCount} 个异常</span>}
            </div>
          )}
        </div>
      )}

      <Handle
        type="target"
        position={Position.Top}
        id="main-in"
        className="!h-1.5 !w-1.5 !border-0 !opacity-0"
        style={{ backgroundColor: data.accent }}
      />
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

const semanticNodeTypes = { semantic: SemanticGraphNode };

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
  const graph = useMemo(
    () => buildSemanticGraph(workflow, trace, selectedNodeId, onOpenArtifact),
    [workflow, trace, selectedNodeId, onOpenArtifact],
  );
  const sourceEventTypeCounts = useMemo(() => trace.events.reduce<Record<string, number>>(
    (counts, event) => ({ ...counts, [event.event_type]: (counts[event.event_type] || 0) + 1 }),
    {},
  ), [trace.events]);

  const focusNode = (nodeId: string, zoom = READING_ZOOM) => {
    setSelectedNodeId(nodeId);
    const target = graph.nodes.find((node) => node.id === nodeId && node.data?.nodeKind === 'semantic');
    if (!flowInstance || !target) return;
    void flowInstance.setCenter(
      target.position.x + SEMANTIC_NODE_WIDTH / 2,
      target.position.y + SEMANTIC_NODE_HEIGHT / 2,
      { zoom, duration: 320 },
    );
  };

  useEffect(() => {
    const openingNodes = graph.nodes
      .filter((node) => node.data?.nodeKind === 'semantic')
      .slice(0, 3);
    if (!flowInstance || openingNodes.length === 0) return;
    void flowInstance.fitView({
      nodes: openingNodes,
      padding: 0.08,
      minZoom: 0.82,
      maxZoom: READING_ZOOM,
      duration: 0,
    });
  }, [flowInstance, workflow?.inference_run.inference_id]);

  if (!workflow) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-xl rounded-3xl border border-line bg-white/80 p-8 text-center shadow-lg">
          <div className="text-accent font-mono text-xs uppercase">Semantic Workflow</div>
          <h2 className="font-serif text-3xl mt-3">尚未生成语义工作流</h2>
          <p className="text-muted text-sm leading-6 mt-3">
            模型会读取六类 Event，执行阶段边界判断、逐阶段语义总结、关系提取和证据验证。命令、工具、子 Agent 与控制事件会作为不同证据处理。
          </p>
          <label className="block text-left text-xs text-muted mt-6">
            Node 总结颗粒度要求
            <textarea
              value={annotationGuidance}
              onChange={(event) => setAnnotationGuidance(event.target.value)}
              maxLength={1000}
              rows={4}
              placeholder="例如：每个 Node 只保留一个核心目标、两句行为摘要和最多三条关键结果；保留数字和限制。"
              className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-ink text-sm resize-none"
            />
            <span className="block mt-1">仅控制语义表述详略，不改变 Episode 边界和证据约束。</span>
          </label>
          <div className="flex items-center justify-center mt-4">
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(annotationGuidance)}
              className="px-5 py-2.5 rounded-full bg-accent text-white text-sm disabled:opacity-50"
            >
              使用语义模型生成
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
              从 Episode {progress.failed_episode || '失败位置'} 继续处理
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 grid grid-cols-[240px_minmax(620px,1fr)_320px] gap-2.5 p-2.5">
      <aside className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg flex flex-col">
        <div className="px-4 py-3 border-b border-line bg-white/70">
          <div className="flex items-center justify-between">
            <span className="ot-section-title">语义节点 · {workflow.semantic_nodes.length}</span>
          </div>
          <div className="ot-meta text-muted mt-1">
            {workflow.inference_run.method} · {workflow.source_events?.event_count || workflow.inference_run.source_event_count || trace.events.length} events → {workflow.inference_run.candidate_count ?? '—'} candidates
          </div>
          <label className="block text-[10px] text-muted mt-3">
            Node 总结颗粒度要求
            <textarea
              value={annotationGuidance}
              onChange={(event) => setAnnotationGuidance(event.target.value)}
              maxLength={1000}
              rows={3}
              className="w-full mt-1 px-2.5 py-2 rounded-lg border border-line bg-white text-ink text-xs resize-none"
            />
          </label>
          <div className="mt-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(annotationGuidance)}
              className="w-full px-2 py-1.5 rounded-lg bg-accent text-white text-[10px] disabled:opacity-40"
            >
              模型重新生成
            </button>
          </div>
          {(loading || ['running', 'scheduled', 'retrying', 'partial'].includes(progress?.status || '')) && (
            <SemanticProgressBar progress={progress} compact />
          )}
          {progress?.status === 'partial' && progress.retryable && progress.inference_id && (
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(annotationGuidance, progress.inference_id)}
              className="w-full mt-2 px-2 py-1.5 rounded-lg bg-orange-100 text-orange-800 text-[10px] font-semibold disabled:opacity-40"
            >
              继续未完成分析
            </button>
          )}
        </div>
        <div className="flex-1 overflow-auto">
          {workflow.semantic_nodes.map((node) => (
            <div
              key={node.node_id}
              className={`border-b border-line p-3 ${selectedNodeId === node.node_id ? 'bg-orange-50' : 'hover:bg-white'}`}
            >
              <div className="flex items-start gap-2">
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => focusNode(node.node_id)}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] text-accent">NODE {node.sequence}</span>
                    <span className="ot-meta text-muted">{node.primary_activity}</span>
                  </div>
                  <div className="font-semibold text-sm mt-1">{node.title}</div>
                  <div className="ot-meta text-muted mt-2 line-clamp-2">{node.objective.value}</div>
                  <div className="flex gap-1 mt-2">
                    {node.errors.length > 0 && <Badge text={`${node.errors.length} error`} tone="red" />}
                    {node.review_status !== 'unreviewed' && <Badge text={node.review_status} tone="green" />}
                    <Badge text={`${node.outcome_claims.length} outcomes`} tone="gray" />
                  </div>
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <section className="min-h-0 grid grid-rows-[66px_1fr] gap-2.5">
        <div className="grid grid-cols-5 gap-2 p-2 border border-line rounded-3xl bg-white/70">
          <SemanticMetric label="源 Events" value={workflow.source_events?.event_count || workflow.validation.source_event_count || trace.events.length} />
          <SemanticMetric label="语义节点" value={workflow.semantic_nodes.length} />
          <SemanticMetric label="Tool" value={workflow.source_events?.event_type_counts?.tool_execution ?? sourceEventTypeCounts.tool_execution ?? 0} />
          <SemanticMetric label="Command" value={workflow.source_events?.event_type_counts?.command_execution ?? sourceEventTypeCounts.command_execution ?? 0} />
          <SemanticMetric label="Subagent" value={workflow.source_events?.event_type_counts?.subagent_result ?? sourceEventTypeCounts.subagent_result ?? 0} />
        </div>
        <div className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
          <div className="h-12 px-4 border-b border-line bg-white/60 flex items-center justify-between gap-3">
            <span className="ot-section-title">证据驱动语义工作流</span>
            <div className="flex items-center gap-2">
              <span className="hidden xl:inline ot-meta text-muted">仅显示 NEXT 阶段主干</span>
              <button
                type="button"
                disabled={!selectedNodeId}
                onClick={() => selectedNodeId && focusNode(selectedNodeId)}
                className="rounded-full border border-line bg-white px-3 py-1 text-[11px] font-semibold text-[#675e56] shadow-sm hover:border-accent disabled:opacity-40"
              >
                定位当前
              </button>
              <button
                type="button"
                onClick={() => void flowInstance?.fitView({ padding: 0.1, minZoom: 0.14, maxZoom: 0.55, duration: 320 })}
                className="rounded-full border border-line bg-white px-3 py-1 text-[11px] font-semibold text-[#675e56] shadow-sm hover:border-accent"
              >
                全览
              </button>
            </div>
          </div>
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            nodeTypes={semanticNodeTypes}
            defaultViewport={{ x: 80, y: 12, zoom: READING_ZOOM }}
            minZoom={0.14}
            maxZoom={1.25}
            nodesDraggable={false}
            onInit={setFlowInstance}
            onNodeClick={(_, node) => {
              if (node.data?.nodeKind === 'semantic') focusNode(node.id);
            }}
          >
            <Background color="rgba(217,119,69,0.08)" gap={26} />
            <Controls />
            <MiniMap nodeColor="#d97745" />
          </ReactFlow>
        </div>
      </section>

      <aside className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
        {selectedNode ? (
          <SemanticNodeInspector
            node={selectedNode}
            trace={trace}
            workflow={workflow}
            onEvidence={onEvidence}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-muted text-sm">请选择语义节点</div>
        )}
      </aside>
    </div>
  );
}

function SemanticNodeInspector({
  node,
  trace,
  workflow,
  onEvidence,
}: {
  node: SemanticNode;
  trace: ObserverTrace;
  workflow: SemanticWorkflow;
  onEvidence: (eventId: string) => void;
}) {
  const evidence = node.event_ids
    .map((eventId) => trace.events.find((event) => event.event_id === eventId))
    .filter((event): event is NonNullable<typeof event> => Boolean(event));
  const episodeCandidates = new Set(
    workflow.episodes
      .filter((episode) => node.episode_ids.includes(episode.episode_id))
      .flatMap((episode) => episode.candidate_episode_ids),
  );
  const boundaryDecisions = (workflow.boundary_decisions || []).filter((decision) => (
    episodeCandidates.has(decision.left_candidate_id)
    || episodeCandidates.has(decision.right_candidate_id)
  ));
  const orchestrationTools = new Set(['TaskCreate', 'TaskUpdate', 'TaskGet', 'TaskList', 'Skill']);
  const isOrchestration = (action: SemanticNode['actions'][number]) => (
    action.semantic_relevance === 'orchestration' || orchestrationTools.has(action.tool_name)
  );
  const keyActions = node.actions.filter((action) => !isOrchestration(action));
  const orchestrationActions = node.actions.filter(isOrchestration);
  const resources = node.observed_inputs
    .map((item) => String(item.value || ''))
    .filter(Boolean);
  const eventTypeCounts = Object.keys(node.event_profile?.event_type_counts || {}).length
    ? node.event_profile?.event_type_counts || {}
    : evidence.reduce<Record<string, number>>(
        (counts, event) => ({ ...counts, [event.event_type]: (counts[event.event_type] || 0) + 1 }),
        {},
      );

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-line bg-white/60">
        <div className="flex items-center justify-between">
          <span className="ot-meta font-mono text-accent">SEMANTIC NODE {node.sequence}</span>
          <span className="ot-meta text-muted">{node.origin} · {node.inference_method}</span>
        </div>
        <h2 className="font-serif text-2xl mt-2">{node.title}</h2>
        <div className="ot-meta text-muted mt-2">
          {node.primary_activity} · {node.review_status}
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px] font-mono text-[#675e56]">
          <span className="rounded-full bg-stone-100 px-2 py-1">{node.event_profile?.event_count || node.event_ids.length} Events</span>
          {(eventTypeCounts.tool_execution || 0) > 0 && <span className="rounded-full bg-violet-50 px-2 py-1">{eventTypeCounts.tool_execution} Tools</span>}
          {(eventTypeCounts.command_execution || 0) > 0 && <span className="rounded-full bg-orange-50 px-2 py-1">{eventTypeCounts.command_execution} Commands</span>}
          {(eventTypeCounts.subagent_result || 0) > 0 && <span className="rounded-full bg-cyan-50 px-2 py-1">{eventTypeCounts.subagent_result} Subagents</span>}
          {(eventTypeCounts.control_event || 0) > 0 && <span className="rounded-full bg-amber-50 px-2 py-1">{eventTypeCounts.control_event} Controls</span>}
        </div>
      </div>
      <div className="flex-1 overflow-auto p-5 space-y-5">
        <section>
          <h3 className="ot-section-title mb-2">阶段目标</h3>
          <p className="rounded-xl border border-line bg-white p-3 text-sm leading-6">
            {node.objective.value}
          </p>
        </section>

        <section>
          <h3 className="ot-section-title mb-2">行为摘要</h3>
          <p className="rounded-xl border border-line bg-white p-3 text-sm leading-6">
            {node.summary.value}
          </p>
        </section>

        <section>
          <h3 className="ot-section-title mb-2">Agent 报告的结果</h3>
          <p className="text-xs text-muted mb-2">忠实呈现 Agent、Subagent 或工具在记录中给出的结果，不代表 Observer 另行事实认证。</p>
          {node.outcome_claims.length ? node.outcome_claims.map((claim, index) => (
            <div key={index} className="rounded-xl border border-line bg-white p-3 text-sm leading-6 mb-2">
              {claim.text}
              <div className="ot-meta text-muted mt-2">记录内置信度 {claim.confidence_level}</div>
            </div>
          )) : <div className="text-sm text-muted">该阶段没有明确输出结果。</div>}
        </section>

        {(keyActions.length > 0 || resources.length > 0 || node.errors.length > 0) && (
          <section>
            <h3 className="ot-section-title mb-2">关键动作与资源</h3>
            {keyActions.map((action) => (
              <button key={action.event_id} type="button" onClick={() => onEvidence(action.event_id)} className="w-full text-left rounded-xl border border-line bg-white p-3 mb-2">
                <div className="flex justify-between gap-2 text-sm"><span className="font-semibold">{action.action_name || action.tool_name}</span><span>{action.status}</span></div>
                <div className="ot-meta text-accent mt-1">{actionTypeLabel(action.action_type, action.event_type)}{action.event_subtype ? ` · ${action.event_subtype}` : ''}</div>
                <div className="ot-meta text-muted mt-1">{action.summary}</div>
              </button>
            ))}
            {resources.map((resource) => (
              <div key={resource} className="rounded-xl border border-line bg-stone-50 px-3 py-2 mb-2 text-xs font-mono break-all">{resource}</div>
            ))}
            {node.errors.map((error) => (
              <div key={error.event_id} className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800 mb-2">
                {error.summary || '工具错误'} · {error.recovered ? '后续已恢复' : '未观察到恢复'}
              </div>
            ))}
          </section>
        )}

        <details className="rounded-2xl border border-line bg-white/60 p-3">
          <summary className="ot-section-title cursor-pointer">技术审计与原始证据</summary>
          <div className="mt-4 space-y-5">
          <section>
          <h3 className="ot-section-title mb-2">Confidence & Validation</h3>
          <div className="rounded-xl border border-line bg-white p-3 text-xs space-y-1">
            <div>Model confidence：{node.confidence.model_level || node.confidence.level}</div>
            <div>Validated confidence：{node.confidence.validated_level || node.confidence.level}</div>
            <div>关键事件引用覆盖率：{(node.confidence.evidence_coverage * 100).toFixed(1)}%</div>
          </div>
          {workflow.validation.issues.length > 0 && (
            <div className="mt-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">
              {workflow.validation.issues.slice(0, 6).map((issue, index) => (
                <div key={index}>{String(issue.code || 'validation_issue')}</div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h3 className="ot-section-title mb-2">Boundary Audit</h3>
          {boundaryDecisions.length ? boundaryDecisions.map((decision) => (
            <div key={`${decision.left_candidate_id}-${decision.right_candidate_id}`} className="rounded-xl border border-line bg-white p-3 mb-2 text-xs">
              <div className="flex justify-between gap-2 font-mono">
                <span>{decision.model_decision || '—'} → {decision.effective_decision}</span>
                <span>{decision.decision_origin}</span>
              </div>
              <div className="text-muted mt-1">{decision.override_reason || decision.reason || '无边界说明'}</div>
            </div>
          )) : <div className="text-sm text-muted">该节点没有相邻边界决策。</div>}
        </section>

        <section>
          <h3 className="ot-section-title mb-2">编排动作</h3>
          {orchestrationActions.map((action) => (
            <button key={action.event_id} type="button" onClick={() => onEvidence(action.event_id)} className="w-full text-left rounded-xl border border-line bg-white p-3 mb-2">
              <div className="flex justify-between gap-2 text-sm"><span className="font-semibold">{action.action_name || action.tool_name}</span><span>{action.status}</span></div>
              <div className="ot-meta text-muted mt-1">{action.summary}</div>
            </button>
          ))}
          {!orchestrationActions.length && <div className="text-sm text-muted">没有编排动作。</div>}
        </section>

        <section>
          <h3 className="ot-section-title mb-2">Evidence</h3>
          {evidence.map((event) => (
            <button key={event.event_id} type="button" onClick={() => onEvidence(event.event_id)} className="w-full text-left px-3 py-2 border-b border-line hover:bg-white">
              <div className="text-xs font-semibold">#{event.sequence} {event.title}</div>
              <div className="ot-meta text-accent mt-1">{event.event_type}{event.event_subtype ? ` · ${event.event_subtype}` : ''}</div>
              <div className="ot-meta text-muted mt-1">line {event.source_lines.join(', ')} · {event.summary}</div>
            </button>
          ))}
        </section>
          </div>
        </details>
      </div>
    </div>
  );
}

function buildSemanticGraph(
  workflow: SemanticWorkflow | null,
  trace: ObserverTrace,
  selectedNodeId: string | null,
  onOpenArtifact: (artifactId: string) => Promise<void>,
): { nodes: Node[]; edges: Edge[] } {
  if (!workflow) return { nodes: [], edges: [] };
  const layout = new dagre.graphlib.Graph();
  layout.setGraph({ rankdir: 'TB', ranksep: 54, nodesep: 56, marginx: 36, marginy: 36 });
  layout.setDefaultEdgeLabel(() => ({}));
  workflow.semantic_nodes.forEach((node) => layout.setNode(node.node_id, {
    width: SEMANTIC_NODE_WIDTH,
    height: SEMANTIC_NODE_HEIGHT,
  }));
  workflow.relations
    .filter((relation) => relation.type === 'NEXT')
    .forEach((relation) => layout.setEdge(relation.from_node_id, relation.to_node_id));
  const artifactLinks = (trace.artifacts || []).flatMap((artifact) => (
    workflow.semantic_nodes.flatMap((semanticNode) => {
      const eventIds = new Set(semanticNode.event_ids);
      const operations = artifact.operations.filter((item) => eventIds.has(item.event_id));
      if (!operations.length) return [];
      return [{ artifact, semanticNode, operations }];
    })
  ));
  const linkedArtifacts = [...new Map(
    artifactLinks.map((item) => [item.artifact.artifact_id, item.artifact]),
  ).values()];
  dagre.layout(layout);

  const nodes = workflow.semantic_nodes.map<Node>((semanticNode) => {
    const position = layout.node(semanticNode.node_id) || { x: 0, y: 0 };
    const artifactCount = new Set(
      artifactLinks
        .filter((item) => item.semanticNode.node_id === semanticNode.node_id)
        .map((item) => item.artifact.artifact_id),
    ).size;
    const fallbackEventTypeCounts = semanticNode.event_ids.reduce<Record<string, number>>((counts, eventId) => {
      const eventType = trace.events.find((event) => event.event_id === eventId)?.event_type;
      return eventType ? { ...counts, [eventType]: (counts[eventType] || 0) + 1 } : counts;
    }, {});
    const eventTypeCounts = Object.keys(semanticNode.event_profile?.event_type_counts || {}).length
      ? semanticNode.event_profile?.event_type_counts || {}
      : fallbackEventTypeCounts;
    return {
      id: semanticNode.node_id,
      type: 'semantic',
      selected: selectedNodeId === semanticNode.node_id,
      position: {
        x: Math.round(position.x - SEMANTIC_NODE_WIDTH / 2),
        y: Math.round(position.y - SEMANTIC_NODE_HEIGHT / 2),
      },
      data: {
        nodeKind: 'semantic',
        sequence: semanticNode.sequence,
        activity: semanticNode.primary_activity,
        activityLabel: activityLabel(semanticNode.primary_activity),
        title: semanticNode.title,
        eventCount: semanticNode.event_profile?.event_count || semanticNode.event_ids.length,
        toolCount: eventTypeCounts.tool_execution ?? 0,
        commandCount: eventTypeCounts.command_execution ?? 0,
        outcomeCount: semanticNode.outcome_claims.length,
        artifactCount,
        errorCount: semanticNode.errors.length,
        reviewStatus: semanticNode.review_status,
        origin: semanticNode.origin,
        accent: activityColor(semanticNode.primary_activity),
      },
      style: { width: SEMANTIC_NODE_WIDTH, height: SEMANTIC_NODE_HEIGHT },
    };
  });
  const artifactNodes = linkedArtifacts.map<Node>((artifact) => {
    const primaryLink = artifactLinks.find(
      (item) => item.artifact.artifact_id === artifact.artifact_id,
    );
    const producerPosition = primaryLink
      ? layout.node(primaryLink.semanticNode.node_id)
      : { x: 0, y: 0 };
    const siblings = primaryLink
      ? artifactLinks.filter(
          (item) => item.semanticNode.node_id === primaryLink.semanticNode.node_id,
        )
      : [];
    const index = Math.max(
      0,
      siblings.findIndex((item) => item.artifact.artifact_id === artifact.artifact_id),
    );
    const rowCount = Math.ceil(Math.max(1, siblings.length) / 2);
    const column = index % 2;
    const row = Math.floor(index / 2);
    return {
      id: artifact.artifact_id,
      position: {
        x: Math.round(producerPosition.x + 192 + column * 214),
        y: Math.round(producerPosition.y - 33 + (row - (rowCount - 1) / 2) * 82),
      },
      targetPosition: Position.Left,
      data: {
        nodeKind: 'artifact',
        label: (
          <button
            type="button"
            title={artifact.path}
            onClick={(event) => {
              event.stopPropagation();
              void onOpenArtifact(artifact.artifact_id);
            }}
              className="nodrag block w-full overflow-hidden text-left text-inherit"
            >
            <span className="block text-[10px] font-mono uppercase opacity-70">
              {artifactTypeLabel(artifact.artifact_type)}
            </span>
            <span className="mt-1 block truncate font-semibold" title={artifact.name}>{artifact.name}</span>
            <span className="mt-1 block text-[10px] opacity-60">本地打开 ↗</span>
          </button>
        ),
      },
      style: {
        width: 196,
        height: 66,
        overflow: 'hidden',
        borderRadius: 14,
        border: `2px solid ${artifactColor(artifact.artifact_type)}`,
        background: '#ffffff',
        textAlign: 'left',
        fontSize: 12,
        lineHeight: 1.25,
        boxShadow: '0 6px 16px rgba(76,55,32,0.08)',
      },
    };
  });
  const semanticEdges = workflow.relations
    .filter((relation) => relation.type === 'NEXT')
    .map<Edge>((relation) => ({
      id: relation.relation_id,
      source: relation.from_node_id,
      target: relation.to_node_id,
      type: 'smoothstep',
      sourceHandle: 'main-out',
      targetHandle: 'main-in',
      animated: false,
      style: {
        stroke: '#d97745',
        strokeWidth: 2.2,
        opacity: 0.82,
      },
    }));
  const artifactEdges = artifactLinks.map<Edge>(({ artifact, semanticNode, operations }) => {
    const modified = operations.some((item) => item.operation === 'modified');
    return {
      id: `artifact-edge-${semanticNode.node_id}-${artifact.artifact_id}`,
      source: semanticNode.node_id,
      target: artifact.artifact_id,
      sourceHandle: 'artifact-out',
      label: modified ? '修改' : '生成',
      type: 'smoothstep',
      style: { stroke: artifactColor(artifact.artifact_type), strokeWidth: 1.8 },
      labelStyle: { fontSize: 9, fill: '#57534e' },
    };
  });
  return { nodes: [...nodes, ...artifactNodes], edges: [...semanticEdges, ...artifactEdges] };
}

function artifactTypeLabel(type: string): string {
  if (type === 'dataset') return '数据文件';
  if (type === 'report') return '报告';
  if (type === 'visualization') return '可视化';
  if (type === 'code') return '代码';
  return '文件';
}

function artifactColor(type: string): string {
  if (type === 'dataset') return '#2563eb';
  if (type === 'report') return '#d97745';
  if (type === 'visualization') return '#7c3aed';
  if (type === 'code') return '#0f766e';
  return '#78716c';
}

function activityColor(activity: string): string {
  if (activity === 'Validation' || activity === 'Refinement') return '#7c3aed';
  if (activity === 'Communication' || activity === 'Synthesis') return '#d97745';
  if (activity === 'Task Understanding' || activity === 'Data Understanding') return '#0f766e';
  if (activity === 'Analysis' || activity === 'Exploration') return '#2563eb';
  return '#78716c';
}

function activityLabel(activity: string): string {
  const labels: Record<string, string> = {
    Exploration: '探索',
    'Data Understanding': '数据理解',
    'Data Preparation': '数据准备',
    'Task Understanding': '任务理解',
    Analysis: '分析',
    Communication: '交付',
    Synthesis: '综合',
    Validation: '验证',
    Refinement: '修订',
  };
  return labels[activity] || activity;
}

function actionTypeLabel(actionType?: string, eventType?: string): string {
  if (actionType === 'command' || eventType === 'command_execution') return 'Agent Command';
  if (actionType === 'subagent' || eventType === 'subagent_result') return 'Subagent Result';
  if (actionType === 'control' || eventType === 'control_event') return 'Control Event';
  return 'Tool Execution';
}

function Badge({ text, tone }: { text: string; tone: 'red' | 'green' | 'gray' }) {
  const style = tone === 'red'
    ? 'text-red-700 bg-red-50'
    : tone === 'green'
    ? 'text-green-700 bg-green-50'
    : 'text-muted bg-stone-100';
  return <span className={`px-2 py-0.5 rounded-full text-[9px] font-mono ${style}`}>{text}</span>;
}

function SemanticMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-2 rounded-2xl border border-line bg-white/80 px-3 py-2">
      <div className="truncate ot-meta text-muted">{label}</div>
      <div className="shrink-0 ot-stat text-[21px]">{value}</div>
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
  return (
    <div className={compact ? 'mt-2' : 'mt-6 text-left'}>
      <div className="flex items-center justify-between gap-3 text-[10px] font-mono text-muted mb-1">
        <span>{progress?.message || '正在启动语义处理'}</span>
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
          Episode {progress.current}/{progress.total} · {progress.stage}
        </div>
      )}
      {!compact && progress?.status === 'partial' && (
        <div className="text-[10px] text-orange-700 mt-2">
          已完成 {progress.completed_episode_count ?? 0}/{progress.total ?? '—'} 个 Episode；
          当前结果已保存，可从检查点继续。
        </div>
      )}
    </div>
  );
}
