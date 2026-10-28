import assert from 'node:assert/strict';
import test from 'node:test';
import { eventNodeSize, eventRoleLabel, eventRelationLabels, mergeEventRelations, validateImportedEventWorkflow, validateLiveEventWorkflow, projectEventStory, layoutEventStory } from '../frontend/src/utils/eventWorkflow.ts';

const trace = { session: { session_id: 'demo' }, events: ['a', 'b', 'c'].map((event_id, sequence) => ({ event_id, sequence, event_type: sequence ? 'model_response' : 'user_prompt', turn_id: 'turn' })),
  relations: [{ relation_id: 'r1', from: 'a', to: 'b', type: 'invokes', origin: 'derived' }, { relation_id: 'r2', from: 'b', to: 'c', type: 'result_feeds', origin: 'derived' }] };
test('logical labels merge with explicit calls, and contrary edges cannot make cycles', () => {
  const workflow = { logical_relations: [
    { relation_id: 'l1', from: 'a', to: 'b', type: 'TRIGGERS', origin: 'inferred', label: '触发分析', confidence: 'high' },
    { relation_id: 'l2', from: 'b', to: 'a', type: 'TRIGGERS', origin: 'inferred', label: '错误回边', confidence: 'high' },
  ] };
  const result = mergeEventRelations(trace, workflow);
  const pair = result.relations.filter(r => r.from === 'a' && r.to === 'b');
  assert.equal(pair.length, 1);
  assert.equal(pair[0].kind, 'logical');
  assert.equal(pair[0].label, '触发分析');
  assert.deepEqual(pair[0].rule_types, ['invokes']);
  assert.equal(result.warnings.length, 1);
  assert.equal(result.relations.some(r => r.from === 'b' && r.to === 'a'), false);
});
test('three sizes express weight without deleting background events', () => {
  assert.ok(eventNodeSize('core', true).width > eventNodeSize('supporting', true).width);
  assert.ok(eventNodeSize('supporting', true).height > eventNodeSize('background', true).height);
  assert.deepEqual(eventNodeSize('core', false), eventNodeSize('background', false));
  assert.equal(mergeEventRelations(trace, null).relations.length, 2);
});
test('four behavior roles preserve result prominence without translating legacy grades', () => {
  for (const role of ['key_decision', 'key_turning_point', 'key_result']) {
    assert.ok(eventNodeSize(role, true).height > eventNodeSize('normal_execution', true).height);
    assert.deepEqual(eventNodeSize(role, false), eventNodeSize('normal_execution', false));
  }
  assert.equal(eventRoleLabel('key_result'), '关键结果');
  assert.match(eventRoleLabel('core'), /旧版/);
});
test('v03 imports require four-role annotations and still enforce accepted relation reviews', () => {
  const value = { schema_version: 'event-workflow/0.3', catalog_version: 'event-relations/0.2', session_id: 'demo', validation: { valid: true },
    event_summaries: trace.events.map(({event_id})=>({event_id})), logical_relations: [], relation_assessments: [],
    event_importance: trace.events.map(({event_id}, i)=>({event_id, level:['key_decision','normal_execution','key_result'][i], reason:'任务行为依据', confidence:'medium', related_event_ids:[]})) };
  assert.equal(validateImportedEventWorkflow(value, trace), value);
  assert.throws(()=>validateImportedEventWorkflow({...value, event_importance:value.event_importance.map(e=>({...e,level:'core'}))}, trace));
  assert.throws(()=>validateImportedEventWorkflow({...value, relation_assessments:undefined}, trace));
  const merged=mergeEventRelations(trace,{...value, logical_relations:[{relation_id:'candidate',from:'a',to:'c',type:'SUPPORTS_RESULT',review_status:'candidate',confidence:'high'}]});
  assert.equal(merged.relations.some(r=>r.kind==='logical'), false);
});
test('imported workflow must cover the exact current session events', () => {
  const value = { schema_version: 'event-workflow/0.1', session_id: 'demo', validation: { valid: true },
    event_summaries: trace.events.map(({ event_id }) => ({ event_id })), event_importance: trace.events.map(({ event_id }) => ({ event_id })), logical_relations: [] };
  assert.equal(validateImportedEventWorkflow(value, trace), value);
  assert.throws(() => validateImportedEventWorkflow({ ...value, event_importance: value.event_importance.slice(1) }, trace));
  assert.throws(() => validateImportedEventWorkflow({ ...value, session_id: 'other' }, trace));
});

test('new workflow draws only accepted non-low relations', () => {
  const relations = [
    { relation_id: 'accepted', from: 'a', to: 'b', type: 'GUIDES_METHOD', label: '落实方法', confidence: 'medium', review_status: 'accepted' },
    { relation_id: 'candidate', from: 'a', to: 'c', type: 'PROVIDES_INPUT', label: '未确认消费', confidence: 'medium', review_status: 'candidate' },
    { relation_id: 'rejected', from: 'b', to: 'c', type: 'LEADS_TO_VALIDATION', label: '审批不是验证', confidence: 'high', review_status: 'rejected' },
    { relation_id: 'low', from: 'a', to: 'c', type: 'TRIGGERS', label: '低置信度', confidence: 'low', review_status: 'accepted' },
  ];
  const result = mergeEventRelations(trace, { schema_version: 'event-workflow/0.2', logical_relations: relations });
  assert.deepEqual(result.relations.filter(r => r.kind === 'logical').map(r => r.relation_id), ['accepted']);
  assert.equal(result.relations.find(r => r.from === 'b' && r.to === 'c').kind, 'rule');
  assert.equal(Object.keys(eventRelationLabels).length, 13);
});

test('new workflow imports require reviewed catalog relations and retain candidates', () => {
  const relation = { relation_id: 'reviewed', from: 'a', to: 'b', type: 'GUIDES_METHOD', label: '方法落实',
    review_status: 'accepted', confidence: 'medium', condition_check: 'met', exclusion_check: 'clear',
    connection_basis: 'B 明确落实 A 指定方法', reason: '有采纳依据', limitations: [], evidence_refs: [] };
  const value = { schema_version: 'event-workflow/0.2', catalog_version: 'event-relations/0.2', session_id: 'demo', validation: { valid: true },
    event_summaries: trace.events.map(({ event_id }) => ({ event_id })), event_importance: trace.events.map(({ event_id }) => ({ event_id })),
    logical_relations: [relation], relation_assessments: [relation] };
  assert.equal(validateImportedEventWorkflow(value, trace), value);
  assert.throws(() => validateImportedEventWorkflow({ ...value, catalog_version: 'unknown' }, trace));
  assert.throws(() => validateImportedEventWorkflow({ ...value, relation_assessments: [] }, trace));
  assert.throws(() => validateImportedEventWorkflow({ ...value, logical_relations: [{ ...relation, review_status: 'candidate' }] }, trace));
  assert.throws(() => validateImportedEventWorkflow({ ...value, relation_assessments: [{ ...relation, type: 'MADE_UP' }] }, trace));
});

const storyTrace = {
  session: { session_id: 'story' }, artifacts: [],
  events: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((event_id, sequence) => ({
    event_id, sequence: sequence + 1, event_type: event_id === 'a' ? 'user_prompt' : event_id === 'g' ? 'subagent_result' : event_id === 'c' ? 'tool_execution' : 'model_response',
    turn_id: 'turn', scope: { turn_id: 'turn', ...(event_id === 'g' ? { task_id: 'verify' } : {}) },
    actor: { type: event_id === 'g' ? 'subagent' : 'agent', id: event_id === 'g' ? 'verify' : 'main' },
    payload: event_id === 'c' ? { name: 'Read' } : {},
  })),
  relations: ['a-b', 'b-c', 'c-d', 'd-e', 'e-f', 'f-g'].map((pair, index) => ({
    relation_id: `rule-${index}`, from: pair[0], to: pair[2], type: index === 5 ? 'spawns' : index % 2 ? 'invokes' : 'result_feeds', origin: 'derived',
  })),
};
const storyWorkflow = {
  schema_version: 'event-workflow/0.2', event_importance: storyTrace.events.map(({ event_id }) => ({ event_id, level: ['a', 'e', 'g', 'h'].includes(event_id) ? 'core' : event_id === 'c' ? 'supporting' : 'background' })),
  logical_relations: [
    { relation_id: 'verify', from: 'e', to: 'g', type: 'LEADS_TO_VALIDATION', label: '复核结果', review_status: 'accepted', confidence: 'high', origin: 'inferred' },
    { relation_id: 'merge', from: 'g', to: 'h', type: 'CONTRIBUTES_TO_MERGE', label: '复核纳入报告', review_status: 'accepted', confidence: 'high', origin: 'inferred' },
  ],
};
test('main view retains every Event either individually or in a traceable process group', () => {
  const story = projectEventStory(storyTrace, storyWorkflow, 'main');
  assert.equal(story.visibleEventCount, 4);
  assert.equal(story.foldedEventCount, 4);
  assert.deepEqual(story.groups.map(g => g.event_ids), [['b', 'c', 'd'], ['f']]);
  const ids = story.units.flatMap(u => u.event ? [u.id] : u.group.event_ids);
  assert.deepEqual(ids, storyTrace.events.map(e => e.event_id));
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(story.edges.some(edge => edge.grouped));
  for (const edge of story.edges) {
    for (const relation of edge.relations) assert.ok([...storyTrace.relations, ...storyWorkflow.logical_relations].some(original => original.relation_id === relation.relation_id));
  }
  assert.equal(story.edges.some(edge => edge.from === 'a' && edge.to === 'e'), false, 'never invent a direct core-to-core edge');
});
test('expanded processes restore original endpoints while keeping lane positions stable', () => {
  const closed = projectEventStory(storyTrace, storyWorkflow, 'main');
  const group = closed.groups[0];
  const opened = projectEventStory(storyTrace, storyWorkflow, 'main', new Set([group.id]));
  assert.equal(opened.visibleEventCount, 7);
  assert.equal(opened.foldedEventCount, 1);
  assert.ok(opened.edges.some(edge => edge.from === 'b' && edge.to === 'c'));
  assert.ok(opened.edges.some(edge => edge.from === 'c' && edge.to === 'd'));
  const firstLayout = layoutEventStory(closed, storyWorkflow, new Set(), true);
  const expandedLayout = layoutEventStory(opened, storyWorkflow, new Set([group.id]), true);
  assert.deepEqual(firstLayout.positions.get('a'), expandedLayout.positions.get('a'));
  closed.units.forEach(unit => assert.equal(firstLayout.positions.get(unit.id).x + firstLayout.sizes.get(unit.id).width / 2,
    expandedLayout.positions.get(unit.id).x + expandedLayout.sizes.get(unit.id).width / 2));
  assert.ok(expandedLayout.sizes.get(group.id).height > firstLayout.sizes.get(group.id).height);
  assert.ok(expandedLayout.positions.get('e').y > firstLayout.positions.get('e').y);
});
test('fixed lanes honor DAG direction, identified subagents and deterministic order', () => {
  const story = projectEventStory(storyTrace, storyWorkflow, 'main');
  const layout = layoutEventStory(story, storyWorkflow, new Set(), true);
  assert.ok(layout.positions.get('g').x > layout.positions.get('e').x);
  assert.equal(layout.positions.get('a').x, layout.positions.get('e').x);
  story.edges.forEach(edge => assert.ok(layout.positions.get(edge.from).y < layout.positions.get(edge.to).y));
  const shuffled = { ...storyTrace, events: [...storyTrace.events].reverse(), relations: [...storyTrace.relations].reverse() };
  const shuffledStory = projectEventStory(shuffled, storyWorkflow, 'main');
  assert.deepEqual(shuffledStory.units.map(u => u.id), story.units.map(u => u.id));
  assert.deepEqual([...layoutEventStory(shuffledStory, storyWorkflow, new Set(), true).positions], [...layout.positions]);
});
test('full view and raw sessions retain every Event and original execution connection', () => {
  for (const workflow of [storyWorkflow, null]) {
    const story = projectEventStory(storyTrace, workflow, 'full');
    assert.equal(story.units.length, 8);
    assert.equal(story.groups.length, 0);
    assert.equal(story.foldedEventCount, 0);
    storyTrace.relations.forEach(relation => assert.ok(story.edges.some(edge => edge.relations.some(r => r.relation_id === relation.relation_id))));
  }
});
test('separate task anchors remain separate without inferred dependencies', () => {
  const disconnected = { ...storyTrace, events: storyTrace.events.filter(e => ['a', 'h'].includes(e.event_id)).map(e => ({ ...e, turn_id: e.event_id, scope: { turn_id: e.event_id } })), relations: [] };
  const story = projectEventStory(disconnected, storyWorkflow, 'main');
  assert.equal(story.edges.length, 0);
  assert.equal(story.units.length, 2);
});

test('live workflow covers exactly completed turns while a new turn is still running',()=>{
  const source={...trace,events:[...trace.events,{event_id:'new',sequence:4,event_type:'user_prompt',turn_id:'next'}]};
  const workflow={schema_version:'event-workflow/0.3',catalog_version:'event-relations/0.2',session_id:'demo',validation:{valid:true},
    scope:{type:'completed_turns',cross_turn_inference:false,turns:[{turn_id:'turn',revision:1}]},
    event_summaries:trace.events.map(e=>({event_id:e.event_id})),logical_relations:[],relation_assessments:[],
    event_importance:trace.events.map(e=>({event_id:e.event_id,level:'normal_execution',reason:'本轮执行',confidence:'medium',related_event_ids:[]}))};
  assert.equal(validateLiveEventWorkflow(workflow,source),workflow);
  assert.throws(()=>validateImportedEventWorkflow(workflow,source),'file import remains strict');
  assert.throws(()=>validateLiveEventWorkflow({...workflow,event_summaries:workflow.event_summaries.slice(1)},source));
  assert.throws(()=>validateLiveEventWorkflow({...workflow,scope:{...workflow.scope,cross_turn_inference:true}},source));
  assert.throws(()=>validateLiveEventWorkflow(workflow,{...source,events:[...source.events,{event_id:'late',turn_id:'turn'}]}),'late fact must invalidate the old partial result');
});
