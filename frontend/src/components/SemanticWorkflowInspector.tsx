import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { ObserverTrace } from '../types/observer';
import type { SemanticNode, SemanticSwimlaneGroup, SemanticWorkflow } from '../types/semantic';
import { semanticLanes, swimlaneEdgeLabel } from '../utils/semanticSwimlanes';

export type SemanticInspectorTab = 'overview' | 'stages';

interface Props {
  group: SemanticSwimlaneGroup;
  node: SemanticNode;
  trace: ObserverTrace;
  workflow: SemanticWorkflow;
  aggregated: boolean;
  tab: SemanticInspectorTab;
  onTabChange: (tab: SemanticInspectorTab) => void;
  onSelect: (id: string) => void;
  onEvidence: (id: string) => void;
  onClose: () => void;
}

function ExpandableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const paragraph = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const element = paragraph.current;
    if (!element) return;
    const measure = () => { if (!expanded) setTruncated(element.scrollHeight > element.clientHeight + 1); };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, expanded]);
  return <div>
    <p ref={paragraph} className={expanded ? 'semantic-detail-text' : 'semantic-detail-text semantic-detail-clamped'}>{text}</p>
    {truncated && <button type="button" className="semantic-detail-text-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? '收起全文' : '展开全文'}</button>}
  </div>;
}

const orchestrationTools = new Set(['TaskCreate', 'TaskUpdate', 'TaskGet', 'TaskList', 'Skill']);
const isOrchestration = (action: SemanticNode['actions'][number]) =>
  action.semantic_relevance === 'orchestration' || orchestrationTools.has(action.tool_name);

function ActionList({ actions, onEvidence }: { actions: SemanticNode['actions']; onEvidence: Props['onEvidence'] }) {
  return <div className="semantic-detail-actions">
    {actions.map(action => <button key={action.event_id} type="button" className="semantic-detail-action" onClick={() => onEvidence(action.event_id)} title={action.summary} aria-label={`查看 ${toolLabel(action.action_name || action.tool_name)} 原始记录`}>
      <span className="semantic-detail-action-head"><strong>{toolLabel(action.action_name || action.tool_name)}</strong><span>{statusLabel(action.status)}</span></span>
      <span className="semantic-detail-action-summary">{action.summary || actionTypeLabel(action.action_type, action.event_type)}</span>
    </button>)}
  </div>;
}

export default function SemanticWorkflowInspector({ group, node, trace, workflow, aggregated, tab, onTabChange, onSelect, onEvidence, onClose }: Props) {
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { if (body.current) body.current.scrollTop = 0; }, [group.group_id, node.node_id, tab]);
  const members = group.node_ids.map(id => workflow.semantic_nodes.find(item => item.node_id === id)).filter((item): item is SemanticNode => Boolean(item));
  const groupEvents = new Set(members.flatMap(item => item.event_ids));
  const evidence = node.event_ids.map(id => trace.events.find(event => event.event_id === id)).filter((event): event is NonNullable<typeof event> => Boolean(event));
  const episodeCandidates = new Set(workflow.episodes.filter(episode => node.episode_ids.includes(episode.episode_id)).flatMap(episode => episode.candidate_episode_ids));
  const boundaries = (workflow.boundary_decisions || []).filter(decision => episodeCandidates.has(decision.left_candidate_id) || episodeCandidates.has(decision.right_candidate_id));
  const keyActions = node.actions.filter(action => !isOrchestration(action));
  const orchestrationActions = node.actions.filter(isOrchestration);
  const resources = node.observed_inputs.map(item => String(item.value || '')).filter(Boolean);
  const counts = Object.keys(node.event_profile?.event_type_counts || {}).length ? node.event_profile!.event_type_counts : evidence.reduce<Record<string, number>>((result, event) => ({ ...result, [event.event_type]: (result[event.event_type] || 0) + 1 }), {});
  const allClaims = members.flatMap(member => member.outcome_claims.map(claim => ({ ...claim, member })));
  const claims = [...new Map(allClaims.map(claim => [claim.text, claim])).values()];
  const groupActions = [...new Map(members.flatMap(member => member.actions.filter(action => !isOrchestration(action))).map(action => [action.event_id, action])).values()];

  const tabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const next = event.key === 'Home' ? 'overview' : event.key === 'End' ? 'stages' : ['ArrowLeft', 'ArrowRight'].includes(event.key) ? (tab === 'overview' ? 'stages' : 'overview') : null;
    if (!next) return;
    event.preventDefault();
    onTabChange(next);
    event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-tab="${next}"]`)?.focus();
  };

  return <>
    <header className="semantic-detail-header">
      <div className="semantic-detail-title-row"><h2 title={group.title}>{group.title}</h2><button type="button" className="semantic-dismiss" aria-label="收起阶段详情" onClick={onClose}>×</button></div>
      <div className="semantic-detail-meta">{semanticLanes.find(lane => lane.id === group.lane)?.title} · {members.length} 个原阶段 · {groupEvents.size} 条记录</div>
    </header>
    <div className="semantic-detail-tabs" role="tablist" aria-label="详情内容">
      {(['overview', 'stages'] as const).map(value => <button key={value} type="button" role="tab" id={`semantic-detail-${value}`} data-tab={value} aria-selected={tab === value} aria-controls="semantic-detail-panel" tabIndex={tab === value ? 0 : -1} onKeyDown={tabKey} onClick={() => onTabChange(value)}>{value === 'overview' ? '聚合概览' : `原阶段（${members.length}）`}</button>)}
    </div>
    <div ref={body} key={`${group.group_id}-${tab}`} id="semantic-detail-panel" className="semantic-detail-body" role="tabpanel" aria-labelledby={`semantic-detail-${tab}`} tabIndex={0}>
      {tab === 'overview' ? <>
        <section className="semantic-detail-section"><h3>行为摘要</h3><ExpandableText text={group.summary} /></section>
        <section className="semantic-detail-section">
          <h3>记录中的结果</h3>
          {claims.length ? <>
            {claims.slice(0, 3).map(claim => <div className="semantic-detail-result" key={claim.text}><p>{claim.text}</p><button type="button" className="semantic-detail-source" onClick={() => { onSelect(claim.member.node_id); onTabChange('stages'); }}>来源：原阶段 #{claim.member.sequence}</button></div>)}
            {claims.length > 3 && <details className="semantic-detail-disclosure"><summary>其余结果（{claims.length - 3}）</summary>{claims.slice(3).map(claim => <div className="semantic-detail-result" key={claim.text}><p>{claim.text}</p><button type="button" className="semantic-detail-source" onClick={() => { onSelect(claim.member.node_id); onTabChange('stages'); }}>来源：原阶段 #{claim.member.sequence}</button></div>)}</details>}
          </> : <p className="semantic-detail-empty">暂无明确的已记录结果。</p>}
        </section>
        {groupActions.length > 0 && <section className="semantic-detail-section"><h3>关键动作</h3><ActionList actions={groupActions.slice(0, 3)} onEvidence={onEvidence} />{groupActions.length > 3 && <details className="semantic-detail-disclosure"><summary>其余动作（{groupActions.length - 3}）</summary><ActionList actions={groupActions.slice(3)} onEvidence={onEvidence} /></details>}</section>}
        {members.some(member => member.errors.length) && <section className="semantic-detail-section"><h3>异常与恢复</h3>{members.flatMap(member => member.errors).map(error => <p key={error.event_id} className="semantic-detail-error">{error.summary || '工具错误'} · {error.recovered ? '后续已恢复' : '未观察到恢复'}</p>)}</section>}
        <details className="semantic-detail-disclosure"><summary>依据与证据</summary><p className="semantic-detail-caption">{aggregated ? 'AI 聚合解释' : '已有阶段归类'} · 置信度 {confidenceLabel(group.confidence)}</p><p className="semantic-detail-text">{group.reason}</p><p className="semantic-detail-caption">来源阶段：{members.map(member => `#${member.sequence}`).join('、')}</p><button type="button" className="semantic-detail-source" onClick={() => onTabChange('stages')}>查看原阶段与原始证据</button></details>
      </> : <>
        <div className="semantic-detail-stage-picker">
          {members.length > 3 ? <label>选择原阶段<select aria-label="选择原阶段" value={node.node_id} onChange={event => onSelect(event.target.value)}>{members.map(member => <option key={member.node_id} value={member.node_id}>#{member.sequence} {member.title}</option>)}</select></label> : members.length > 1 ? <div className="semantic-detail-stage-chips" aria-label="选择原阶段">{members.map(member => <button type="button" key={member.node_id} aria-pressed={member.node_id === node.node_id} onClick={() => onSelect(member.node_id)} title={`#${member.sequence} ${member.title}`}><span>#{member.sequence}</span><span>{member.title}</span></button>)}</div> : <p className="semantic-detail-caption">原阶段 #{node.sequence} · {node.title}</p>}
        </div>
        <div className="semantic-detail-stats"><span>{node.event_ids.length} 条记录</span>{(counts.tool_execution || 0) > 0 && <span>{counts.tool_execution} 次工具调用</span>}{(counts.command_execution || 0) > 0 && <span>{counts.command_execution} 条命令</span>}{(counts.subagent_result || 0) > 0 && <span>{counts.subagent_result} 个子任务</span>}{(counts.control_event || 0) > 0 && <span>{counts.control_event} 次流程变化</span>}</div>
        <section className="semantic-detail-section"><h3>阶段目标</h3><p className="semantic-detail-text">{node.objective.value}</p></section>
        <section className="semantic-detail-section"><h3>执行摘要</h3><ExpandableText key={node.node_id} text={node.summary.value} /></section>
        {keyActions.length > 0 && <section className="semantic-detail-section"><h3>关键动作与资源</h3><ActionList actions={keyActions} onEvidence={onEvidence} /></section>}
        {resources.length > 0 && <details className="semantic-detail-disclosure"><summary>输入资源（{resources.length}）</summary>{resources.map((resource, index) => <p key={index} className="semantic-detail-resource">{resource}</p>)}</details>}
        {node.errors.length > 0 && <section className="semantic-detail-section"><h3>异常与恢复</h3>{node.errors.map(error => <p key={error.event_id} className="semantic-detail-error">{error.summary || '工具错误'} · {error.recovered ? '后续已恢复' : '未观察到恢复'}</p>)}</section>}
        <section className="semantic-detail-section"><h3>记录中的结果</h3><p className="semantic-detail-caption">来自对话、工具和子任务的已记录结果。</p>{node.outcome_claims.length ? node.outcome_claims.map((claim, index) => <div key={index} className="semantic-detail-result"><p>{claim.text}</p>{claim.confidence_level === 'low' && <small>低置信度</small>}</div>) : <p className="semantic-detail-empty">这个阶段暂无明确结果。</p>}</section>
        <details key={node.node_id} className="semantic-detail-disclosure"><summary>依据与证据</summary>
          <section className="semantic-detail-section"><h3>来源与复核</h3><p className="semantic-detail-caption">{activityLabel(node.primary_activity)} · {node.inference_method === 'model' ? '模型整理' : '规则整理'} · {reviewLabel(node.review_status)}</p></section>
          <section className="semantic-detail-section"><h3>置信度与校验</h3><p className="semantic-detail-text">模型：{confidenceLabel(node.confidence.model_level || node.confidence.level)} · 校验后：{confidenceLabel(node.confidence.validated_level || node.confidence.level)}</p><p className="semantic-detail-caption">关键事件引用覆盖率：{(node.confidence.evidence_coverage * 100).toFixed(1)}%</p>{node.confidence.uncertainty_reason && <p className="semantic-detail-text">{node.confidence.uncertainty_reason}</p>}{node.outcome_claims.map((claim, index) => <p key={index} className="semantic-detail-caption">结果 {index + 1} 的置信度：{confidenceLabel(claim.confidence_level)}</p>)}{workflow.validation.issues.length > 0 && <details className="semantic-detail-disclosure"><summary>工作流校验提示（{workflow.validation.issues.length}）</summary>{workflow.validation.issues.map((issue, index) => <p key={index} className="semantic-detail-error">{String(issue.code || 'validation_issue')}</p>)}</details>}</section>
          <section className="semantic-detail-section"><h3>阶段边界</h3>{boundaries.length ? boundaries.map(decision => <div key={`${decision.left_candidate_id}-${decision.right_candidate_id}`} className="semantic-detail-result"><p>{decision.model_decision || '—'} → {decision.effective_decision} · {decision.decision_origin}</p><p className="semantic-detail-caption">{decision.override_reason || decision.reason || '无边界说明'}</p></div>) : <p className="semantic-detail-empty">没有相邻边界决策。</p>}</section>
          <section className="semantic-detail-section"><h3>编排动作</h3>{orchestrationActions.length ? <ActionList actions={orchestrationActions} onEvidence={onEvidence} /> : <p className="semantic-detail-empty">没有编排动作。</p>}</section>
          <section className="semantic-detail-section"><h3>已有阶段关系</h3>{workflow.relations.filter(relation => relation.from_node_id === node.node_id || relation.to_node_id === node.node_id).map(relation => <div key={relation.relation_id} className="semantic-detail-result"><p>{workflow.semantic_nodes.find(item => item.node_id === relation.from_node_id)?.title} → {workflow.semantic_nodes.find(item => item.node_id === relation.to_node_id)?.title}</p><p className="semantic-detail-caption">{swimlaneEdgeLabel(relation.type)} · {relation.origin} · 置信度 {confidenceLabel(relation.confidence_level)}</p>{relation.type !== 'NEXT' && <p className="semantic-detail-caption">保留原语义引用方向，不表示时间前后。</p>}{relation.evidence_event_ids.map(id => <button type="button" key={id} className="semantic-detail-source" onClick={() => onEvidence(id)}>查看证据</button>)}</div>)}</section>
          <section className="semantic-detail-section"><h3>原始证据</h3>{evidence.map(event => <button type="button" key={event.event_id} className="semantic-detail-evidence" onClick={() => onEvidence(event.event_id)}><strong>#{event.sequence} {event.title}</strong><span>{event.event_type}{event.event_subtype ? ` · ${event.event_subtype}` : ''}</span><span>line {event.source_lines.join(', ')} · {event.summary}</span></button>)}</section>
        </details>
      </>}
    </div>
  </>;
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
    Visualization: '可视化',
    Implementation: '实现',
    Uncertain: '待解释',
  };
  return labels[activity] || activity;
}

function actionTypeLabel(actionType?: string, eventType?: string): string {
  if (actionType === 'command' || eventType === 'command_execution') return '命令执行';
  if (actionType === 'subagent' || eventType === 'subagent_result') return '子任务结果';
  if (actionType === 'control' || eventType === 'control_event') return '流程事件';
  return '工具调用';
}

function reviewLabel(status: string): string {
  return ({ unreviewed: '待复核', accepted: '已确认', corrected: '已修订', rejected: '待修订' } as Record<string, string>)[status] || status;
}

function toolLabel(name: string): string {
  return ({ Read: '读取文件', Write: '写入文件', Edit: '修改文件', Glob: '查找文件', Grep: '搜索内容', Bash: '执行命令', Agent: '委派子任务', TaskOutput: '读取子任务结果', TaskCreate: '创建任务', TaskUpdate: '更新任务', Skill: '加载技能' } as Record<string, string>)[name] || name;
}

function statusLabel(status: string): string {
  return ({ success: '完成', completed: '完成', error: '异常', pending: '等待', running: '进行中', interrupted: '已中断', unknown: '状态未知' } as Record<string, string>)[status] || status;
}

function confidenceLabel(level: string): string {
  return ({ high: '高', medium: '中', low: '低' } as Record<string, string>)[level] || level;
}
