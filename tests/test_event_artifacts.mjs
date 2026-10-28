import assert from 'node:assert/strict';
import test from 'node:test';
import { indexEventArtifacts } from '../frontend/src/utils/eventArtifacts.ts';
import { layoutEventTurns } from '../frontend/src/utils/eventTurns.ts';
import { routeEventRelations, segmentHitsRect } from '../frontend/src/utils/eventRouting.ts';

test('session identifiers survive artifact ordering and repeated file interactions', () => {
  const events = ['a', 'b', 'c'].map((event_id, sequence) => ({ event_id, sequence }));
  const artifact = (id, type, ops) => ({ artifact_id: id, path: id, name: id, artifact_type: type, exists: true, operations: ops.map(([event_id, operation]) => ({ event_id, operation })), evidence_event_ids: [] });
  const artifacts = [artifact('script.ts', 'code', [['a','read'], ['a','modified'], ['b','executed']]), artifact('raw.csv', 'dataset', [['a','read']]), artifact('clean.csv', 'dataset', [['c','created']])];
  const original = JSON.stringify(artifacts);
  const index = indexEventArtifacts({ events, artifacts: artifacts.toReversed() });
  assert.deepEqual(index.artifacts.map(a => a.label).sort(), ['代码1', '数据集1', '数据集2'].sort());
  assert.equal(index.byEvent.get('a').filter(a => a.artifact.artifact_id === 'script.ts').length, 1);
  assert.deepEqual(index.byEvent.get('a').find(a => a.artifact.artifact_id === 'script.ts').operations, ['读取','修改']);
  assert.equal(index.byEvent.get('b')[0].artifact.label, '代码1');
  assert.equal(index.byEvent.get('c')[0].artifact.label, '数据集2');
  assert.equal(JSON.stringify(artifacts), original);
});

test('artifact footer participates in layout and edge avoidance', () => {
  const events = ['a','b','c'].map((event_id, sequence) => ({ event_id, sequence, event_type: 'model_response', scope: {turn_id:'t'}, payload:{} }));
  const trace = { events, turns:[{turn_id:'t',prompt_event_id:'a',event_ids:['a','b','c']}], artifacts:[] };
  const relations = [{relation_id:'r1',from:'a',to:'b',kind:'rule',type:'invokes'}, {relation_id:'r2',from:'b',to:'c',kind:'rule',type:'invokes'}];
  const plain = layoutEventTurns(trace, null, relations, true);
  const layout = layoutEventTurns(trace, null, relations, true, new Set(['b']));
  assert.equal(layout.sizes.get('b').height, plain.sizes.get('b').height + 30);
  assert.equal(layout.sizes.get('a').height, plain.sizes.get('a').height);
  const rects = events.map(e => {const turn=layout.turns[0], p=layout.positions.get(e.event_id);return {x:turn.x+p.x,y:turn.y+p.y,...layout.sizes.get(e.event_id)};});
  for (const route of routeEventRelations(layout, events, relations, null).values()) for(let i=1;i<route.points.length;i++) for(const rect of rects) assert.equal(segmentHitsRect(route.points[i-1], route.points[i], rect),false);
});
