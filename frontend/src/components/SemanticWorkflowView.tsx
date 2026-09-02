import { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Edge, MiniMap, Node } from 'reactflow';
import dagre from 'dagre';
import { ObserverTrace } from '../types/observer';
import { SemanticNode, SemanticProgress, SemanticWorkflow } from '../types/semantic';

const ACTIVITIES = [
  'Task Understanding',
  'Data Understanding',
  'Data Preparation',
  'Exploration',
  'Analysis',
  'Visualization',
  'Validation',
  'Refinement',
  'Synthesis',
  'Communication',
  'Uncertain',
];

interface SemanticWorkflowViewProps {
  sessionId: string;
  trace: ObserverTrace;
  workflow: SemanticWorkflow | null;
  loading: boolean;
  progress: SemanticProgress | null;
  onGenerate: (rulesOnly: boolean) => Promise<void>;
  onWorkflowChange: (workflow: SemanticWorkflow) => void;
  onEvidence: (eventId: string) => void;
  onError: (message: string) => void;
}

export default function SemanticWorkflowView({
  sessionId,
  trace,
  workflow,
  loading,
  progress,
  onGenerate,
  onWorkflowChange,
  onEvidence,
  onError,
}: SemanticWorkflowViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [mergeNodeIds, setMergeNodeIds] = useState<string[]>([]);

  useEffect(() => {
    setSelectedNodeId((current) => (
      current && workflow?.semantic_nodes.some((node) => node.node_id === current)
        ? current
        : workflow?.semantic_nodes[0]?.node_id || null
    ));
    setMergeNodeIds((current) => current.filter((nodeId) => (
      workflow?.semantic_nodes.some((node) => node.node_id === nodeId)
    )));
  }, [workflow?.inference_run.inference_id, workflow?.review.review_event_count]);

  const selectedNode = workflow?.semantic_nodes.find((node) => node.node_id === selectedNodeId) || null;
  const graph = useMemo(
    () => buildSemanticGraph(workflow, selectedNodeId),
    [workflow, selectedNodeId],
  );

  async function submitReview(action: string, payload: Record<string, unknown>) {
    try {
      const response = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/semantic/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, payload }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
      onWorkflowChange(body.workflow as SemanticWorkflow);
    } catch (reviewError) {
      onError(reviewError instanceof Error ? reviewError.message : '人工校正失败');
    }
  }

  if (!workflow) {
    return (
      <div className="h-full flex items-center justify-center p-8">
        <div className="max-w-xl rounded-3xl border border-line bg-white/80 p-8 text-center shadow-lg">
          <div className="text-accent font-mono text-xs uppercase">Semantic Workflow</div>
          <h2 className="font-serif text-3xl mt-3">尚未生成语义工作流</h2>
          <p className="text-muted text-sm leading-6 mt-3">
            模型模式会执行 Episode 边界调整、语义标注、关系提取和证据验证；规则模式不需要外部 API，适合先检查页面与证据映射。
          </p>
          <div className="flex items-center justify-center gap-3 mt-6">
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(false)}
              className="px-5 py-2.5 rounded-full bg-accent text-white text-sm disabled:opacity-50"
            >
              使用语义模型生成
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(true)}
              className="px-5 py-2.5 rounded-full border border-line-strong bg-white text-sm disabled:opacity-50"
            >
              生成保守规则版
            </button>
          </div>
          {(loading || progress) && <SemanticProgressBar progress={progress} />}
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
          <div className="flex flex-wrap gap-1.5 mt-2">
            <ValidationBadge
              label="Evidence"
              valid={workflow.validation.evidence_valid ?? workflow.validation.valid}
            />
            <ValidationBadge
              label="Granularity"
              valid={workflow.validation.granularity_valid ?? workflow.validation.valid}
            />
          </div>
          <div className="ot-meta text-muted mt-1">
            {workflow.inference_run.method} · {workflow.inference_run.candidate_count ?? '—'} candidates · {workflow.review.review_event_count} 次人工校正
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(false)}
              className="px-2 py-1.5 rounded-lg bg-accent text-white text-[10px] disabled:opacity-40"
            >
              模型重新生成
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => void onGenerate(true)}
              className="px-2 py-1.5 rounded-lg border border-line bg-white text-[10px] disabled:opacity-40"
            >
              规则重新生成
            </button>
          </div>
          {(loading || progress?.status === 'running' || progress?.status === 'scheduled') && (
            <SemanticProgressBar progress={progress} compact />
          )}
        </div>
        <div className="flex-1 overflow-auto">
          {workflow.semantic_nodes.map((node) => (
            <div
              key={node.node_id}
              className={`border-b border-line p-3 ${selectedNodeId === node.node_id ? 'bg-orange-50' : 'hover:bg-white'}`}
            >
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={mergeNodeIds.includes(node.node_id)}
                  onChange={(event) => setMergeNodeIds((current) => (
                    event.target.checked
                      ? [...current, node.node_id]
                      : current.filter((nodeId) => nodeId !== node.node_id)
                  ))}
                  title="选择连续节点进行合并"
                />
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSelectedNodeId(node.node_id)}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] text-accent">NODE {node.sequence}</span>
                    <ConfidencePill level={node.confidence.level} />
                  </div>
                  <div className="font-semibold text-sm mt-1">{node.specific_intent.value}</div>
                  <div className="ot-meta text-muted mt-1">{node.primary_activity}</div>
                  <div className="ot-meta text-muted mt-2 line-clamp-2">{node.summary.value}</div>
                  <div className="flex gap-1 mt-2">
                    {node.errors.length > 0 && <Badge text={`${node.errors.length} error`} tone="red" />}
                    {node.review_status !== 'unreviewed' && <Badge text={node.review_status} tone="green" />}
                    <Badge text={`${node.event_ids.length} evidence`} tone="gray" />
                  </div>
                </button>
              </div>
            </div>
          ))}
        </div>
        <div className="p-3 border-t border-line bg-white/70">
          <button
            type="button"
            disabled={mergeNodeIds.length < 2}
            onClick={() => void submitReview('merge', { node_ids: orderedSelection(workflow, mergeNodeIds) })}
            className="w-full px-3 py-2 rounded-xl border border-line-strong bg-white text-xs disabled:opacity-40"
          >
            合并所选连续节点（{mergeNodeIds.length}）
          </button>
        </div>
      </aside>

      <section className="min-h-0 grid grid-rows-[104px_1fr] gap-3.5">
        <div className="grid grid-cols-5 gap-2.5 p-3 border border-line rounded-3xl bg-white/70">
          <SemanticMetric label="Nodes" value={workflow.semantic_nodes.length} />
          <SemanticMetric label="Episodes" value={workflow.episodes.length} />
          <SemanticMetric label="Relations" value={workflow.relations.length} />
          <SemanticMetric label="Errors" value={workflow.semantic_nodes.reduce((total, node) => total + node.errors.length, 0)} />
          <SemanticMetric label="Coverage" value={`${averageCoverage(workflow)}%`} />
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
            onAccept={() => void submitReview('accept', { node_id: selectedNode.node_id })}
            onUpdate={(payload) => void submitReview('update', { node_id: selectedNode.node_id, ...payload })}
            onSplit={(groups) => void submitReview('split', { node_id: selectedNode.node_id, groups })}
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
  onAccept,
  onUpdate,
  onSplit,
  onEvidence,
}: {
  node: SemanticNode;
  trace: ObserverTrace;
  workflow: SemanticWorkflow;
  onAccept: () => void;
  onUpdate: (payload: Record<string, unknown>) => void;
  onSplit: (groups: Array<Record<string, unknown>>) => void;
  onEvidence: (eventId: string) => void;
}) {
  const [activity, setActivity] = useState(node.primary_activity);
  const [intent, setIntent] = useState(node.specific_intent.value);
  const [summary, setSummary] = useState(node.summary.value);
  const [splitAfter, setSplitAfter] = useState(1);

  useEffect(() => {
    setActivity(node.primary_activity);
    setIntent(node.specific_intent.value);
    setSummary(node.summary.value);
    setSplitAfter(1);
  }, [node.node_id, node.review_status]);

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

  function splitGroups() {
    const left = node.episode_ids.slice(0, splitAfter);
    const right = node.episode_ids.slice(splitAfter);
    onSplit([
      {
        episode_ids: left,
        primary_activity: activity,
        specific_intent: `${intent}（前段）`,
        summary: `${summary}（前段）`,
      },
      {
        episode_ids: right,
        primary_activity: activity,
        specific_intent: `${intent}（后段）`,
        summary: `${summary}（后段）`,
      },
    ]);
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-line bg-white/60">
        <div className="flex items-center justify-between">
          <span className="ot-meta font-mono text-accent">SEMANTIC NODE {node.sequence}</span>
          <ConfidencePill level={node.confidence.level} />
        </div>
        <h2 className="font-serif text-2xl mt-2">{node.specific_intent.value}</h2>
        <div className="ot-meta text-muted mt-2">
          {node.origin} · {node.inference_method} · {node.review_status}
        </div>
      </div>
      <div className="flex-1 overflow-auto p-5 space-y-5">
        <section className="space-y-2">
          <h3 className="ot-section-title">人工接受与修改</h3>
          <label className="block text-xs text-muted">
            Activity
            <select value={activity} onChange={(event) => setActivity(event.target.value)} className="w-full mt-1 px-3 py-2 rounded-xl border border-line bg-white text-ink">
              {ACTIVITIES.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="block text-xs text-muted">
            Specific intent
            <textarea value={intent} onChange={(event) => setIntent(event.target.value)} rows={2} className="w-full mt-1 px-3 py-2 rounded-xl border border-line bg-white text-ink resize-none" />
          </label>
          <label className="block text-xs text-muted">
            Summary
            <textarea value={summary} onChange={(event) => setSummary(event.target.value)} rows={3} className="w-full mt-1 px-3 py-2 rounded-xl border border-line bg-white text-ink resize-none" />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={onAccept} className="px-3 py-2 rounded-xl border border-green-200 bg-green-50 text-green-800 text-xs">接受当前解释</button>
            <button type="button" onClick={() => onUpdate({ primary_activity: activity, specific_intent: intent, summary })} className="px-3 py-2 rounded-xl bg-accent text-white text-xs">保存人工修正</button>
          </div>
          {node.episode_ids.length > 1 && (
            <div className="grid grid-cols-[1fr_auto] gap-2 pt-2">
              <select value={splitAfter} onChange={(event) => setSplitAfter(Number(event.target.value))} className="px-3 py-2 rounded-xl border border-line bg-white text-xs">
                {node.episode_ids.slice(0, -1).map((_, index) => (
                  <option key={index + 1} value={index + 1}>在 Episode {index + 1} 后拆分</option>
                ))}
              </select>
              <button type="button" onClick={splitGroups} className="px-3 py-2 rounded-xl border border-line-strong bg-white text-xs">拆分节点</button>
            </div>
          )}
        </section>

        <section>
          <h3 className="ot-section-title mb-2">Confidence & Validation</h3>
          <div className="rounded-xl border border-line bg-white p-3 text-xs space-y-1">
            <div>Model confidence：{node.confidence.model_level || node.confidence.level}</div>
            <div>Validated confidence：{node.confidence.validated_level || node.confidence.level}</div>
            <div>Evidence coverage：{(node.confidence.evidence_coverage * 100).toFixed(1)}%</div>
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
          <h3 className="ot-section-title mb-2">Outcome</h3>
          {node.outcome_claims.length ? node.outcome_claims.map((claim, index) => (
            <div key={index} className="rounded-xl border border-line bg-white p-3 text-sm mb-2">
              {claim.text}
              <div className="ot-meta text-muted mt-2">{claim.confidence_level} · {claim.evidence_event_ids.length} evidence</div>
            </div>
          )) : <div className="text-sm text-muted">未形成有证据支持的结果声明。</div>}
        </section>

        <section>
          <h3 className="ot-section-title mb-2">Actions & Errors</h3>
          {node.actions.map((action) => (
            <button key={action.event_id} type="button" onClick={() => onEvidence(action.event_id)} className="w-full text-left rounded-xl border border-line bg-white p-3 mb-2">
              <div className="flex justify-between gap-2 text-sm"><span className="font-semibold">{action.tool_name}</span><span>{action.status}</span></div>
              <div className="ot-meta text-muted mt-1">{action.summary}</div>
            </button>
          ))}
          {node.errors.map((error) => (
            <div key={error.event_id} className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800 mb-2">
              {error.summary || '工具错误'} · {error.recovered ? '已恢复' : '未恢复'}
            </div>
          ))}
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
        label: `${semanticNode.primary_activity}\n${semanticNode.specific_intent.value}\n${semanticNode.outcome_claims[0]?.text || ''}`,
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

function ConfidencePill({ level }: { level: string }) {
  const style = level === 'high'
    ? 'text-green-700 bg-green-50 border-green-200'
    : level === 'medium'
    ? 'text-amber-700 bg-amber-50 border-amber-200'
    : 'text-red-700 bg-red-50 border-red-200';
  return <span className={`px-2 py-0.5 rounded-full border text-[9px] font-mono ${style}`}>{level}</span>;
}

function ValidationBadge({ label, valid }: { label: string; valid: boolean }) {
  return (
    <span className={`px-2 py-0.5 rounded-full border text-[9px] font-mono ${
      valid
        ? 'text-green-700 bg-green-50 border-green-200'
        : 'text-red-700 bg-red-50 border-red-200'
    }`}>
      {label}: {valid ? 'VALID' : 'CHECK'}
    </span>
  );
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
    </div>
  );
}

function averageCoverage(workflow: SemanticWorkflow): string {
  if (!workflow.semantic_nodes.length) return '0';
  const average = workflow.semantic_nodes.reduce(
    (total, node) => total + Number(node.confidence.evidence_coverage || 0),
    0,
  ) / workflow.semantic_nodes.length;
  return (average * 100).toFixed(0);
}

function orderedSelection(workflow: SemanticWorkflow, selected: string[]): string[] {
  const selectedSet = new Set(selected);
  return workflow.semantic_nodes
    .filter((node) => selectedSet.has(node.node_id))
    .map((node) => node.node_id);
}
