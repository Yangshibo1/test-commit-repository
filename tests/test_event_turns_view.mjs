import assert from 'node:assert/strict';
import test from 'node:test';
import { groupEventsByTurn, layoutEventTurns } from '../frontend/src/utils/eventTurns.ts';
import { mergeEventRelations } from '../frontend/src/utils/eventWorkflow.ts';

const events = [
  {event_id:'u1',sequence:1,event_type:'user_prompt',scope:{turn_id:'t1'},payload:{content:'先读取数据'}},
  {event_id:'r1',sequence:2,event_type:'tool_execution',scope:{turn_id:'t1'},payload:{}},
  {event_id:'u2',sequence:3,event_type:'user_prompt',scope:{turn_id:'t2'},payload:{content:'再生成图表'}},
  {event_id:'r2',sequence:4,event_type:'tool_execution',scope:{turn_id:'t2'},payload:{}},
  {event_id:'late',sequence:5,event_type:'subagent_result',scope:{turn_id:'t1'},payload:{}},
];
const trace = {events,turns:[
  {turn_id:'t2',prompt_event_id:'u2',prompt:'再生成图表',event_ids:['u2','r2']},
  {turn_id:'t1',prompt_event_id:'u1',prompt:'先读取数据',event_ids:['u1','r1','late']},
],relations:[
  {relation_id:'a',from:'u1',to:'r1',type:'prompts',origin:'derived'},
  {relation_id:'b',from:'u2',to:'r2',type:'prompts',origin:'derived'},
  {relation_id:'c',from:'r1',to:'late',type:'spawns',origin:'derived'},
]};

test('Turn order follows the original task order and preserves late subtask membership', () => {
  const groups=groupEventsByTurn(trace);
  assert.deepEqual(groups.map(g=>g.turn_id),['t1','t2']);
  assert.deepEqual(groups[0].events.map(e=>e.event_id),['u1','r1','late']);
  assert.deepEqual(groups.flatMap(g=>g.events).map(e=>e.event_id).sort(),events.map(e=>e.event_id).sort());
  assert.deepEqual(groups.map(g=>g.ordinal),[1,2]);
});
test('scope overrides stale aliases while recorded membership supports legacy events', () => {
  const source={...trace,events:events.map(e=>e.event_id==='r1'?{...e,turn_id:'t2'}:e.event_id==='r2'?{...e,scope:undefined}:e)};
  const groups=groupEventsByTurn(source);
  assert.ok(groups[0].events.some(e=>e.event_id==='r1'));
  assert.ok(groups[1].events.some(e=>e.event_id==='r2'));
});
test('unscoped events remain visible and are not assigned to a fabricated task', () => {
  const groups=groupEventsByTurn({...trace,events:[{event_id:'control',sequence:0,event_type:'control_event',payload:{}},...events]});
  assert.equal(groups[0].turn_id,null);
  assert.equal(groups[0].ordinal,0);
  assert.equal(groups.flatMap(g=>g.events).length,6);
});
test('independent Turn DAGs align at the top, ordered left to right despite cross-Turn logic', () => {
  const workflow={schema_version:'event-workflow/0.2',event_importance:events.map(e=>({event_id:e.event_id,level:'core'})),logical_relations:[
    {relation_id:'reverse',from:'r2',to:'r1',type:'CHALLENGED_BY',label:'反证',review_status:'accepted',confidence:'high'},
  ]};
  const merged=mergeEventRelations(trace,workflow);
  const layout=layoutEventTurns(trace,workflow,merged.relations,true);
  assert.equal(merged.relations.some(r=>r.relation_id==='reverse'),true,'cross-Turn evidence is retained');
  assert.equal(layout.turns[0].y,layout.turns[1].y);
  assert.ok(layout.turns[1].x>=layout.turns[0].x+layout.turns[0].width+120);
  for(const turn of layout.turns) for(const event of turn.events){
    const p=layout.positions.get(event.event_id),size=layout.sizes.get(event.event_id);
    assert.ok(p.y>=74);
    assert.ok(p.x>=0&&p.x+size.width<=turn.width);
    assert.ok(p.y+size.height<=turn.height);
    assert.equal(layout.eventToTurn.get(event.event_id),turn.id);
  }
  assert.equal(layout.eventToTurn.size,events.length);
});
test('a longer earlier Turn does not push a later Turn down', () => {
  const longer={...trace,events:[...events,{event_id:'extra',sequence:6,event_type:'tool_execution',scope:{turn_id:'t1'},payload:{}}],relations:[...trace.relations,{relation_id:'extra-edge',from:'late',to:'extra',type:'result_feeds',origin:'derived'}]};
  const original=layoutEventTurns(trace,null,mergeEventRelations(trace,null).relations,false);
  const updated=layoutEventTurns(longer,null,mergeEventRelations(longer,null).relations,false);
  assert.ok(updated.turns[0].height>original.turns[0].height);
  const before=original.positions.get('u2'),after=updated.positions.get('u2');
  assert.equal(original.turns[1].y+before.y,updated.turns[1].y+after.y);
});
test('layout-only task anchors never generate new logical or execution relations', () => {
  const source={...trace,relations:[]};
  const relations=[];
  const layout=layoutEventTurns(source,null,relations,false);
  assert.deepEqual(relations,[]);
  for(const turn of layout.turns){
    const task=layout.positions.get(turn.prompt_event_id);
    for(const event of turn.events) if(event.event_id!==turn.prompt_event_id) assert.ok(layout.positions.get(event.event_id).y>task.y);
  }
});
test('importance changes node sizes while keeping Turn order and every Event', () => {
  const workflow={event_importance:events.map(e=>({event_id:e.event_id,level:e.event_id==='r1'?'background':'core'}))};
  const relations=mergeEventRelations(trace,null).relations;
  const weighted=layoutEventTurns(trace,workflow,relations,true);
  const flat=layoutEventTurns(trace,workflow,relations,false);
  assert.deepEqual(weighted.turns.map(t=>t.turn_id),flat.turns.map(t=>t.turn_id));
  assert.ok(weighted.sizes.get('r1').height<weighted.sizes.get('u1').height);
  assert.equal(weighted.positions.size,flat.positions.size);
});

test('secondary events read left to right by sequence on the right wing',()=>{
  const ids=['root','n1','n2','n3','n4','n5','end'];
  const t={events:ids.map((event_id,sequence)=>({event_id,sequence,event_type:'model_response',scope:{turn_id:'t'},payload:{}})),turns:[{turn_id:'t',prompt_event_id:'root',event_ids:ids}],
    relations:ids.slice(1,-1).flatMap(id=>[{relation_id:`in-${id}`,from:'root',to:id,type:'invokes',origin:'derived'},{relation_id:`out-${id}`,from:id,to:'end',type:'result_feeds',origin:'derived'}])};
  const w={event_importance:ids.map((event_id,i)=>({event_id,level:['root','end'].includes(event_id)?'core':i%2?'background':'support'})),logical_relations:[]};
  const l=layoutEventTurns(t,w,mergeEventRelations(t,w).relations,true);
  const center=l.turns[0].centerX, nodes=ids.slice(1,-1).map(id=>({id,x:l.positions.get(id).x+l.sizes.get(id).width/2,y:l.positions.get(id).y+l.sizes.get(id).height/2}));
  assert.ok(nodes.every(n=>n.y===nodes[0].y),'test nodes share one DAG rank despite unequal heights');
  assert.deepEqual([...nodes].sort((a,b)=>a.x-b.x).map(n=>n.id),ids.slice(1,-1));
  assert.ok(nodes.every(n=>n.x>center));
  for(const id of ['root','end'])assert.equal(l.positions.get(id).x+l.sizes.get(id).width/2,center);
});
