import { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, MiniMap, Node } from 'reactflow';
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
}

export default function SemanticWorkflowView({
  trace,
  workflow,
  loading,
  progress,
  onGenerate,
  onEvidence,
}: SemanticWorkflowViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
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
    () => buildSemanticGraph(workflow, selectedNodeId),
    [workflow, selectedNodeId],
  );

  if (!workflow) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-xl rounded-3xl border border-line bg-white/80 p-8 text-center shadow-lg">
          <div className="text-accent font-mono text-xs uppercase">Semantic Workflow</div>
          <h2 className="font-serif text-3xl mt-3">尚未生成语义工作流</h2>
          <p className="text-muted text-sm leading-6 mt-3">
            模型会执行 Episode 边界判断、逐阶段语义总结、关系提取和证据验证。你可以用下方提示词控制 Node 总结的详略程度。
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
    <div className="h-full min-h-0 grid grid-cols-[300px_minmax(620px,1fr)_400px] gap-3.5 p-3.5">
      <aside className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg flex flex-col">
        <div className="px-4 py-3 border-b border-line bg-white/70">
          <div className="flex items-center justify-between">
            <span className="ot-section-title">语义节点 · {workflow.semantic_nodes.length}</span>
          </div>
          <div className="ot-meta text-muted mt-1">
            {workflow.inference_run.method} · {workflow.inference_run.candidate_count ?? '—'} candidates
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
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSelectedNodeId(node.node_id)}>
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

      <section className="min-h-0 grid grid-rows-[104px_1fr] gap-3.5">
        <div className="grid grid-cols-5 gap-2.5 p-3 border border-line rounded-3xl bg-white/70">
          <SemanticMetric label="Nodes" value={workflow.semantic_nodes.length} />
          <SemanticMetric label="Episodes" value={workflow.episodes.length} />
          <SemanticMetric label="Relations" value={workflow.relations.length} />
          <SemanticMetric label="Outcomes" value={workflow.semantic_nodes.reduce((total, node) => total + node.outcome_claims.length, 0)} />
          <SemanticMetric label="Key actions" value={workflow.semantic_nodes.reduce((total, node) => total + node.actions.filter((action) => action.semantic_relevance !== 'orchestration').length, 0)} />
        </div>
        <div className="min-h-0 border border-line rounded-3xl bg-panel overflow-hidden shadow-lg">
          <div className="h-12 px-4 border-b border-line bg-white/60 flex items-center justify-between">
            <span className="ot-section-title">Evidence-grounded Semantic Workflow</span>
            <span className="ot-meta text-muted">NEXT 为布局主干 · 语义关系为虚线</span>
          </div>
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            fitView
            minZoom={0.4}
            maxZoom={1.8}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
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
                <div className="flex justify-between gap-2 text-sm"><span className="font-semibold">{action.tool_name}</span><span>{action.status}</span></div>
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
              <div className="flex justify-between gap-2 text-sm"><span className="font-semibold">{action.tool_name}</span><span>{action.status}</span></div>
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
  selectedNodeId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  if (!workflow) return { nodes: [], edges: [] };
  const layout = new dagre.graphlib.Graph();
  layout.setGraph({ rankdir: 'TB', ranksep: 86, nodesep: 56, marginx: 36, marginy: 36 });
  layout.setDefaultEdgeLabel(() => ({}));
  workflow.semantic_nodes.forEach((node) => layout.setNode(node.node_id, { width: 260, height: 122 }));
  workflow.relations
    .filter((relation) => relation.type === 'NEXT')
    .forEach((relation) => layout.setEdge(relation.from_node_id, relation.to_node_id));
  dagre.layout(layout);

  const nodes = workflow.semantic_nodes.map<Node>((semanticNode) => {
    const position = layout.node(semanticNode.node_id) || { x: 0, y: 0 };
    return {
      id: semanticNode.node_id,
      position: { x: position.x - 130, y: position.y - 61 },
      data: {
        label: `${String(semanticNode.sequence).padStart(2, '0')} · ${semanticNode.primary_activity}\n${semanticNode.title}\n${semanticNode.outcome_claims.length} 项结果`,
      },
      style: {
        width: 260,
        minHeight: 122,
        whiteSpace: 'pre-wrap',
        textAlign: 'left',
        fontSize: 12,
        lineHeight: 1.45,
        borderRadius: 18,
        borderWidth: selectedNodeId === semanticNode.node_id ? 3 : 2,
        borderColor: semanticNode.review_status === 'accepted' ? '#15803d' : activityColor(semanticNode.primary_activity),
        background: semanticNode.origin === 'user_validated' ? '#f0fdf4' : '#fffaf5',
        boxShadow: selectedNodeId === semanticNode.node_id
          ? '0 14px 32px rgba(217,119,69,0.22)'
          : '0 8px 20px rgba(76,55,32,0.08)',
      },
    };
  });
  const edges = workflow.relations.map<Edge>((relation) => {
    const semantic = relation.type !== 'NEXT';
    return {
      id: relation.relation_id,
      source: relation.from_node_id,
      target: relation.to_node_id,
      label: relation.type,
      type: semantic ? 'bezier' : 'smoothstep',
      animated: false,
      style: {
        stroke: semantic ? '#7c3aed' : '#d97745',
        strokeWidth: semantic ? 1.8 : 2.2,
        strokeDasharray: semantic ? '6 4' : undefined,
      },
      labelStyle: { fontSize: 9, fill: semantic ? '#6d28d9' : '#7c5d49' },
    };
  });
  return { nodes, edges };
}

function activityColor(activity: string): string {
  if (activity === 'Validation' || activity === 'Refinement') return '#7c3aed';
  if (activity === 'Communication' || activity === 'Synthesis') return '#d97745';
  if (activity === 'Task Understanding' || activity === 'Data Understanding') return '#0f766e';
  if (activity === 'Analysis' || activity === 'Exploration') return '#2563eb';
  return '#78716c';
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
    <div className="rounded-2xl border border-line bg-white/80 p-3">
      <div className="ot-stat text-[24px]">{value}</div>
      <div className="ot-meta text-muted mt-1">{label}</div>
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
