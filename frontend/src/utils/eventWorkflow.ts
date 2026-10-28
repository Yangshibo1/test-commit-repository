import type { ObserverTrace, ObserverRelation } from '../types/observer';
import type { EventWorkflow, EventImportanceLevel } from '../types/eventWorkflow';

export const eventRelationLabels: Record<string, string> = {
  "PROVIDES_INPUT": "提供输入",
  "GUIDES_METHOD": "指导方法",
  "ENABLES_EXECUTION": "提供执行条件",
  "TRIGGERS": "触发行动",
  "MOTIVATES_INVESTIGATION": "引出调查",
  "LEADS_TO_CORRECTION": "促成修正",
  "LEADS_TO_RETRY": "促成重试",
  "LEADS_TO_VALIDATION": "引出验证",
  "AUTHORIZES": "授权执行",
  "CONTRIBUTES_TO_MERGE": "汇入综合",
  "SUPPORTS_RESULT": "支撑结论",
  "CHALLENGED_BY": "被质疑/反驳",
  "SUPERSEDED_BY": "被替代"
};

export interface DisplayEventRelation extends ObserverRelation {
  kind: 'logical' | 'rule' | 'sequence'; label: string;
  confidence?: string; explanation?: string; rule_types: string[];
}

export const eventBehaviorRoles = ['key_decision', 'normal_execution', 'key_turning_point', 'key_result'] as const;
export function isKeyEvent(level?: EventImportanceLevel) {
  return level === 'core' || level === 'key_decision' || level === 'key_turning_point' || level === 'key_result';
}
export function isRoutineEvent(level?: EventImportanceLevel) {
  return level === 'normal_execution' || level === 'supporting';
}
export function eventRoleLabel(level?: EventImportanceLevel) {
  return level ? ({ key_decision: '关键决策', normal_execution: '正常执行', key_turning_point: '关键转折', key_result: '关键结果', core: '核心（旧版）', supporting: '支撑（旧版）', background: '背景（旧版）' })[level] : '';
}
export function eventRoleColor(level?: EventImportanceLevel) {
  return level ? ({key_decision: '#7c3aed', normal_execution: '#78716c', key_turning_point: '#b45309', key_result: '#047857', core: '#ad5e3b', supporting: '#78716c', background: '#a8a29e'})[level] : '#78716c';
}

export function eventNodeSize(level?: EventImportanceLevel, weighted = false) {
  if (!weighted || !level) return { width: 276, height: 124 };
  if (isKeyEvent(level)) return { width: 310, height: 150 };
  if (isRoutineEvent(level)) return { width: 246, height: 100 };
  return { width: 196, height: 66 };
}

/** Preserve explicit calls, prioritize logical labels, supplement without cycles. */
export function mergeEventRelations(trace: ObserverTrace, workflow: EventWorkflow | null) {
  const ids = new Set(trace.events.map(event => event.event_id));
  const edges = new Map<string, DisplayEventRelation>();
  const adjacency = new Map<string, Set<string>>();
  const warnings: string[] = [];
  const reaches = (start: string, goal: string) => {
    const visited = new Set<string>(); const pending = [start];
    while (pending.length) {
      const node = pending.pop()!;
      if (node === goal) return true;
      if (visited.has(node)) continue;
      visited.add(node); pending.push(...(adjacency.get(node) || []));
    }
    return false;
  };
  const add = (relation: DisplayEventRelation) => {
    if (!ids.has(relation.from) || !ids.has(relation.to) || relation.from === relation.to) return;
    const key = `${relation.from}|${relation.to}`;
    const existing = edges.get(key);
    if (existing) {
      const rules = [...new Set([...existing.rule_types, ...relation.rule_types])];
      if (relation.kind === 'logical' && existing.kind !== 'logical') edges.set(key, { ...relation, rule_types: rules });
      else edges.set(key, { ...existing, rule_types: rules });
      return;
    }
    if (reaches(relation.to, relation.from)) { warnings.push(`未绘制成环的 ${relation.type} 关系`); return; }
    edges.set(key, relation);
    if (!adjacency.has(relation.from)) adjacency.set(relation.from, new Set());
    adjacency.get(relation.from)!.add(relation.to);
  };
  const rule = (relation: ObserverRelation): DisplayEventRelation => ({ ...relation, kind: 'rule', label: '', rule_types: [relation.type] });
  trace.relations.filter(r => ['invokes', 'spawns'].includes(r.type)).forEach(r => add(rule(r)));
  [...(workflow?.logical_relations || [])].filter(r => !['event-workflow/0.2', 'event-workflow/0.3'].includes(workflow?.schema_version || '') || (r.review_status === 'accepted' && r.confidence !== 'low'))
    .sort((a, b) => (a.confidence === 'low' ? 1 : 0) - (b.confidence === 'low' ? 1 : 0))
    .forEach(r => add({ ...r, kind: 'logical', rule_types: [] }));
  trace.relations.filter(r => ['prompts', 'result_feeds', 'depends_on'].includes(r.type)).forEach(r => add(rule(r)));
  const incoming = new Set([...edges.values()].map(r => r.to));
  const previous = new Map<string, string>();
  [...trace.events].sort((a, b) => a.sequence - b.sequence).forEach(event => {
    const turn = event.turn_id || event.scope?.turn_id;
    const prior = turn ? previous.get(turn) : undefined;
    if (prior && event.event_type !== 'user_prompt' && !incoming.has(event.event_id)) {
      add({ relation_id: `sequence-${prior}-${event.event_id}`, from: prior, to: event.event_id,
        type: 'next_fallback', origin: 'derived', kind: 'sequence', label: '', rule_types: [] });
    }
    if (turn) previous.set(turn, event.event_id);
  });
  return { relations: [...edges.values()], warnings };
}

export function validateImportedEventWorkflow(value: EventWorkflow, trace: ObserverTrace) {
  const expected = new Set(trace.events.map(event => event.event_id));
  if (!['event-workflow/0.1', 'event-workflow/0.2', 'event-workflow/0.3'].includes(value.schema_version) || value.session_id !== trace.session.session_id || !value.validation?.valid) throw new Error('请选择当前会话的 event_workflow.json');
  for (const items of [value.event_summaries, value.event_importance]) {
    if (!Array.isArray(items) || items.length !== expected.size || new Set(items.map(item => item.event_id)).size !== expected.size || items.some(item => !expected.has(item.event_id))) throw new Error('AI 结果未完整覆盖当前会话 Event');
  }
  if (!Array.isArray(value.logical_relations) || value.logical_relations.some(r => !expected.has(r.from) || !expected.has(r.to))) throw new Error('AI 关系包含未知 Event');
  if (value.schema_version === 'event-workflow/0.3' && value.event_importance.some(item =>
    !eventBehaviorRoles.some(role => role === item.level) || !item.reason?.trim() || !['high', 'medium', 'low'].includes(item.confidence) ||
    !Array.isArray(item.related_event_ids) || item.related_event_ids.some(id => !expected.has(id)))) throw new Error('行为角色必须完整使用四类新分类并保留理由和置信度');
  if (['event-workflow/0.2', 'event-workflow/0.3'].includes(value.schema_version)) {
    const assessments = value.relation_assessments;
    if (value.catalog_version !== 'event-relations/0.2' || !Array.isArray(assessments)) throw new Error('AI 结果缺少关系规范版本或审查结果');
    const invalidAssessment = assessments.some(r => {
      const invalidContext = r.context_evidence_refs !== undefined &&
        (!Array.isArray(r.context_evidence_refs) || r.context_evidence_refs.some(ref => !expected.has(ref.event_id)));
      return !expected.has(r.from) || !expected.has(r.to) || r.from === r.to ||
        !Object.prototype.hasOwnProperty.call(eventRelationLabels, r.type) ||
        !['accepted', 'candidate', 'rejected'].includes(r.review_status || '') || !r.connection_basis?.trim() ||
        !r.reason?.trim() || !Array.isArray(r.limitations) || !Array.isArray(r.evidence_refs) || invalidContext;
    });
    if (new Set(assessments.map(r => r.relation_id)).size !== assessments.length || invalidAssessment) throw new Error('关系审查结果不完整或类型不符合规范');
    const accepted = assessments.filter(r => r.review_status === 'accepted');
    if (accepted.some(r => r.condition_check !== 'met' || r.exclusion_check !== 'clear' || !['high', 'medium'].includes(r.confidence)) ||
      accepted.length !== value.logical_relations.length || new Set(value.logical_relations.map(r => r.relation_id)).size !== accepted.length ||
      value.logical_relations.some(r => !accepted.some(a => JSON.stringify(a) === JSON.stringify(r)))) throw new Error('主图关系必须完整对应审查通过的关系');
  }
  return value;
}

export type EventStoryMode = 'main' | 'full';
export interface EventProcessGroup {
  id: string; event_ids: string[]; first_sequence: number; last_sequence: number;
  title: string; lane: string;
}
export interface EventStoryUnit {
  id: string; kind: 'event' | 'group'; lane: string;
  event?: ObserverTrace['events'][number]; group?: EventProcessGroup;
}
export interface EventStoryEdge {
  id: string; from: string; to: string; kind: DisplayEventRelation['kind'];
  label: string; grouped: boolean; relations: DisplayEventRelation[];
}

/** Stable topological reading order. Sequence breaks ties; it never invents edges. */
function readingOrder(events: ObserverTrace['events'], relations: DisplayEventRelation[]) {
  const ids = new Set(events.map(e => e.event_id));
  const incoming = new Map(events.map(e => [e.event_id, 0]));
  const outgoing = new Map<string, string[]>();
  for (const relation of relations) {
    if (!ids.has(relation.from) || !ids.has(relation.to)) continue;
    incoming.set(relation.to, incoming.get(relation.to)! + 1);
    outgoing.set(relation.from, [...(outgoing.get(relation.from) || []), relation.to]);
  }
  const byId = new Map(events.map(e => [e.event_id, e]));
  const sort = (a: string, b: string) => byId.get(a)!.sequence - byId.get(b)!.sequence || a.localeCompare(b);
  const pending = events.filter(e => !incoming.get(e.event_id)).map(e => e.event_id).sort(sort);
  const ordered: ObserverTrace['events'] = [];
  while (pending.length) {
    const id = pending.shift()!; ordered.push(byId.get(id)!);
    for (const to of outgoing.get(id) || []) {
      incoming.set(to, incoming.get(to)! - 1);
      if (!incoming.get(to)) { pending.push(to); pending.sort(sort); }
    }
  }
  return ordered;
}

function branchLane(event: ObserverTrace['events'][number]): string | null {
  if (event.actor?.type !== 'subagent' && event.event_type !== 'subagent_result') return null;
  return 'branch:' + (event.scope?.agent_run_id || event.scope?.task_id || event.actor?.id || 'subagent');
}

function processTitle(events: ObserverTrace['events']) {
  if (events.every(e => e.event_type === 'model_response')) return '调用与响应';
  if (events.every(e => e.event_type === 'control_event')) return '系统记录';
  const reads = (e: ObserverTrace['events'][number]) => ['file_read', 'file_search'].includes(e.event_subtype || '') || ['Read', 'Glob', 'Grep'].includes(e.payload?.name);
  if (events.some(reads) && events.every(e => reads(e) || ['model_response', 'control_event'].includes(e.event_type))) return '输入准备与调用';
  return '执行与协调';
}

export function projectEventStory(trace: ObserverTrace, workflow: EventWorkflow | null, mode: EventStoryMode, expanded: Set<string> = new Set()) {
  const merged = mergeEventRelations(trace, workflow);
  const ordered = readingOrder(trace.events, merged.relations);
  const levels = new Map(workflow?.event_importance.map(e => [e.event_id, e.level]) || []);
  const anchors = new Set(ordered.filter(e => isKeyEvent(levels.get(e.event_id)) || e.event_type === 'user_prompt' || e.payload?.is_final).map(e => e.event_id));
  const retained = new Set(anchors);
  const logical = merged.relations.filter(r => r.kind === 'logical');
  const inDegree = new Map<string, number>(), outDegree = new Map<string, number>();
  logical.forEach(r => { inDegree.set(r.to, (inDegree.get(r.to) || 0) + 1); outDegree.set(r.from, (outDegree.get(r.from) || 0) + 1); });
  const importantTypes = new Set(['LEADS_TO_CORRECTION', 'LEADS_TO_VALIDATION', 'CONTRIBUTES_TO_MERGE', 'CHALLENGED_BY', 'SUPERSEDED_BY', 'AUTHORIZES']);
  // Keep meaningful inputs and semantic junctions, not every tool wrapper on a rule path.
  for (const r of logical) {
    if (importantTypes.has(r.type)) {
      for (const id of [r.from, r.to]) if (isRoutineEvent(levels.get(id))) retained.add(id);
    }
  }
  for (const event of ordered) {
    if (isRoutineEvent(levels.get(event.event_id)) && ((inDegree.get(event.event_id) || 0) > 1 || (outDegree.get(event.event_id) || 0) > 1)) retained.add(event.event_id);
  }

  // Select one real shortest connecting path between adjacent anchors. No guessed shortcuts.
  const connectors = new Set<string>();
  const outgoing = new Map<string, DisplayEventRelation[]>();
  merged.relations.filter(r => r.kind !== 'sequence').forEach(r => outgoing.set(r.from, [...(outgoing.get(r.from) || []), r]));
  const anchorEvents = ordered.filter(e => anchors.has(e.event_id));
  for (let index = 1; index < anchorEvents.length; index++) {
    const start = anchorEvents[index - 1], end = anchorEvents[index];
    if ((start.turn_id || start.scope?.turn_id) !== (end.turn_id || end.scope?.turn_id)) continue;
    const pending = [start.event_id], previous = new Map<string, DisplayEventRelation>();
    const visited = new Set(pending);
    while (pending.length && !visited.has(end.event_id)) {
      const id = pending.shift()!;
      const next = [...(outgoing.get(id) || [])].sort((a, b) => Number(b.kind === 'logical') - Number(a.kind === 'logical') || a.relation_id.localeCompare(b.relation_id));
      for (const r of next) if (!visited.has(r.to)) { visited.add(r.to); previous.set(r.to, r); pending.push(r.to); }
    }
    if (!visited.has(end.event_id)) continue;
    for (let id = end.event_id; id !== start.event_id;) {
      const r = previous.get(id)!; connectors.add(r.relation_id);
      id = r.from;
    }
  }

  const units: EventStoryUnit[] = [], groups: EventProcessGroup[] = [];
  const eventToGroup = new Map<string, string>();
  const validationTargets = new Set(logical.filter(r => r.type === 'LEADS_TO_VALIDATION').map(r => r.to));
  const lane = (event: ObserverTrace['events'][number], folded = false) => branchLane(event) ||
    (folded ? 'support' : mode === 'full' || anchors.has(event.event_id) ? 'main' : validationTargets.has(event.event_id) ? 'checks' : 'support');
  let pendingGroup: ObserverTrace['events'] = [];
  const flush = () => {
    if (!pendingGroup.length) return;
    const first = pendingGroup[0], last = pendingGroup[pendingGroup.length - 1];
    const group: EventProcessGroup = { id: `process-${first.event_id}-${last.event_id}`, event_ids: pendingGroup.map(e => e.event_id),
      first_sequence: first.sequence, last_sequence: last.sequence, title: processTitle(pendingGroup), lane: lane(first, true) };
    groups.push(group); units.push({ id: group.id, kind: 'group', group, lane: group.lane });
    group.event_ids.forEach(id => eventToGroup.set(id, group.id)); pendingGroup = [];
  };
  for (const event of ordered) {
    if (mode === 'full' || !workflow || retained.has(event.event_id)) {
      flush(); units.push({ id: event.event_id, kind: 'event', event, lane: lane(event) });
    } else {
      const prior = pendingGroup[pendingGroup.length - 1];
      if (prior && (lane(prior, true) !== lane(event, true) || (prior.turn_id || prior.scope?.turn_id) !== (event.turn_id || event.scope?.turn_id))) flush();
      pendingGroup.push(event);
    }
  }
  flush();
  const visibleId = (id: string) => {
    const group = eventToGroup.get(id); return group && !expanded.has(group) ? group : id;
  };
  const isExpanded = (id: string) => !!eventToGroup.get(id) && expanded.has(eventToGroup.get(id)!);
  const selectedRelations = new Map<string, DisplayEventRelation>();
  const add = (r: DisplayEventRelation) => selectedRelations.set(r.relation_id, r);
  if (mode === 'full' || !workflow) merged.relations.forEach(add);
  else {
    merged.relations.filter(r => r.kind === 'logical' || connectors.has(r.relation_id) || isExpanded(r.from) || isExpanded(r.to)).forEach(add);
    // A folded process gets actual boundary links, not invented causal edges.
    for (const group of groups) {
      if (expanded.has(group.id)) continue;
      const members = new Set(group.event_ids);
      for (const direction of ['in', 'out']) {
        const boundary = merged.relations.filter(r => direction === 'in' ? members.has(r.to) && !members.has(r.from) : members.has(r.from) && !members.has(r.to));
        if (boundary.some(r => selectedRelations.has(r.relation_id))) continue;
        const candidate = boundary.sort((a, b) => Number(a.kind === 'sequence') - Number(b.kind === 'sequence') || a.relation_id.localeCompare(b.relation_id))[0];
        if (candidate) add(candidate);
      }
    }
  }
  const edgeMap = new Map<string, EventStoryEdge>();
  for (const r of selectedRelations.values()) {
    const from = visibleId(r.from), to = visibleId(r.to);
    if (from === to) continue;
    const key = `${from}|${to}|${r.kind}`;
    const prior = edgeMap.get(key);
    if (prior) { prior.relations.push(r); continue; }
    edgeMap.set(key, { id: `story-${r.relation_id}`, from, to, kind: r.kind,
      grouped: from !== r.from || to !== r.to, label: r.label, relations: [r] });
  }
  const edges = [...edgeMap.values()];
  edges.forEach(e => { if (e.relations.length > 1) e.label = `${e.relations.length} 条${e.kind === 'logical' ? '逻辑联系' : '执行连接'}`;
    else if (e.grouped && e.kind === 'logical') e.label = `组内联系 · ${e.label}`; });
  return { units, groups, edges, eventToGroup, warnings: merged.warnings,
    visibleEventCount: units.filter(u => u.kind === 'event').length + groups.filter(g => expanded.has(g.id)).reduce((n, g) => n + g.event_ids.length, 0),
    foldedEventCount: groups.filter(g => !expanded.has(g.id)).reduce((n, g) => n + g.event_ids.length, 0) };
}

/** Fixed lanes + topological rows. Expansion changes row heights, never lane assignments. */
export function layoutEventStory(story: ReturnType<typeof projectEventStory>, workflow: EventWorkflow | null, expanded: Set<string>, weighted: boolean) {
  const levels = new Map(workflow?.event_importance.map(e => [e.event_id, e.level]) || []);
  const branches = [...new Set(story.units.map(u => u.lane).filter(l => l.startsWith('branch:')))];
  const lanes = ['support', 'main', 'checks', ...branches]
    .filter(l => l === 'main' || story.units.some(u => u.lane === l));
  const laneX = new Map<string, number>([['main', 460], ['support', 40], ['checks', 880]]);
  let right = story.units.some(u => u.lane === 'checks') ? 1300 : 880;
  lanes.filter(l => l.startsWith('branch:')).forEach(l => { laneX.set(l, right); right += 420; });
  const sizes = new Map<string, { width: number; height: number }>();
  const childOffsets = new Map<string, { x: number; y: number; width: number; height: number }>();
  for (const unit of story.units) {
    if (unit.event) sizes.set(unit.id, eventNodeSize(levels.get(unit.id), weighted));
    else {
      let height = 82;
      if (expanded.has(unit.id)) {
        for (const id of unit.group!.event_ids) {
          const size = eventNodeSize(levels.get(id), weighted);
          childOffsets.set(id, { x: (334 - size.width) / 2, y: height, ...size }); height += size.height + 16;
        }
        height += 8;
      }
      sizes.set(unit.id, { width: expanded.has(unit.id) ? 334 : 270, height });
    }
  }
  const childToUnit = new Map(story.groups.flatMap(g => g.event_ids.map(id => [id, g.id] as const)));
  const unitId = (id: string) => childToUnit.get(id) || id;
  const parents = new Map<string, Set<string>>();
  story.edges.forEach(e => {
    const from = unitId(e.from), to = unitId(e.to);
    if (from !== to) parents.set(to, new Set([...(parents.get(to) || []), from]));
  });
  const rank = new Map<string, number>(), lastLane = new Map<string, number>();
  let lastMain = 0;
  for (const unit of story.units) {
    const preceding = [...(parents.get(unit.id) || [])].map(id => (rank.get(id) ?? -1) + 1);
    const row = Math.max(0, ...preceding, (lastLane.get(unit.lane) ?? -1) + 1, unit.lane === 'main' ? 0 : lastMain);
    rank.set(unit.id, row); lastLane.set(unit.lane, row);
    if (unit.lane === 'main') lastMain = row;
  }
  const rowHeight = new Map<number, number>();
  story.units.forEach(u => rowHeight.set(rank.get(u.id)!, Math.max(rowHeight.get(rank.get(u.id)!) || 0, sizes.get(u.id)!.height)));
  const rowY = new Map<number, number>(); let y = 64;
  for (let row = 0; row <= Math.max(0, ...rank.values()); row++) { rowY.set(row, y); y += (rowHeight.get(row) || 0) + 66; }
  const positions = new Map(story.units.map(u => [u.id, { x: laneX.get(u.lane)! + (334 - sizes.get(u.id)!.width) / 2, y: rowY.get(rank.get(u.id)!)! }]));
  const rowBottom = new Map(story.units.map(u => [u.id, rowY.get(rank.get(u.id)!)! + (rowHeight.get(rank.get(u.id)!) || 0)]));
  return { positions, sizes, childOffsets, rowBottom, height: y, lanes: lanes.map(id => ({ id, x: laneX.get(id)!,
    label: id === 'main' ? '主流程' : id === 'support' ? '输入与执行过程' : id === 'checks' ? '验证与辅助' : `子任务 ${branches.indexOf(id) + 1}` })) };
}

/** Partial coverage is allowed only for the live API, never for file imports. */
export function validateLiveEventWorkflow(value: EventWorkflow, trace: ObserverTrace) {
  if (value.scope?.type !== 'completed_turns' || value.scope.cross_turn_inference !== false) throw new Error('动态分析结果缺少轮次范围');
  const ids = new Set(value.event_summaries.map(e => e.event_id));
  if ([...ids].some(id => !trace.events.some(e => e.event_id === id))) throw new Error('动态记录正在同步');
  const turns = new Set(value.scope.turns.map(t => t.turn_id));
  const expected = trace.events.filter(e => !e.hidden_by_default && turns.has(e.scope?.turn_id || e.turn_id || ''));
  if (expected.length !== ids.size || expected.some(e => !ids.has(e.event_id))) throw new Error('动态分析结果与本轮记录不一致');
  return validateImportedEventWorkflow(value, {...trace, events:expected});
}
