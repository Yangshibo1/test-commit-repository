import assert from 'node:assert/strict';
import test from 'node:test';
import {projectSemanticSwimlanes,validateSemanticSwimlanes,existingStageLane} from '../frontend/src/utils/semanticSwimlanes.ts';
import {segmentHitsRect} from '../frontend/src/utils/eventRouting.ts';

const workflow={source_trace:{session_id:'session'},inference_run:{inference_id:'stages'},
  episodes:Array.from({length:6},(_,i)=>({episode_id:'ep'+(i+1),turn_id:'t'})),
  semantic_nodes:Array.from({length:6},(_,i)=>({node_id:'n'+(i+1),sequence:i+1,episode_ids:['ep'+(i+1)],primary_activity:['Task Understanding','Planning','Analysis','Analysis','Refinement','Communication'][i],title:'原阶段'+(i+1),summary:{value:'行为摘要'},confidence:{level:'medium'}})),
  relations:Array.from({length:5},(_,i)=>({relation_id:'next'+i,from_node_id:'n'+(i+1),to_node_id:'n'+(i+2),type:'NEXT',origin:'derived',evidence_event_ids:['event'+i],confidence_level:'high'})).concat([{relation_id:'fix',from_node_id:'n5',to_node_id:'n3',type:'REFINES',origin:'inferred',evidence_event_ids:['event5'],confidence_level:'medium'}])};
const aggregation={schema_version:'semantic-swimlanes/0.1',session_id:'session',source_inference_id:'stages',validation:{valid:true},groups:
  [['input',['n1']],['planning',['n2']],['execution',['n3','n4']],['revision',['n5']],['execution',['n6']]].map(([lane,node_ids],i)=>({group_id:'g'+i,lane,node_ids,title:'共同子目标',summary:'保留关键结果',reason:'同一连续目标',confidence:'medium'}))};

test('four fixed columns share forward rows and move down when returning to execution',()=>{
  const p=projectSemanticSwimlanes(workflow,aggregation);
  assert.deepEqual(p.lanes.map(l=>l.id),['input','planning','execution','revision']);
  assert.equal(p.units[0].y,p.units[3].y);
  assert.ok(p.units[4].y>p.units[3].y);
  assert.equal(p.units[2].x,p.units[4].x);
  assert.equal(new Set(p.units.flatMap(u=>u.node_ids)).size,6);
  assert.ok(p.height<6*(156+52));
});
test('projection retains original relations and directions without adding causal edges',()=>{
  const p=projectSemanticSwimlanes(workflow,aggregation);
  const fix=p.edges.find(e=>e.type==='REFINES');assert.equal(fix.from,'g3');assert.equal(fix.to,'g2');
  const internal=workflow.relations.find(r=>r.from_node_id==='n3'&&r.to_node_id==='n4');
  const refs=p.edges.flatMap(e=>e.relation_ids);
  assert.deepEqual(new Set(refs),new Set(workflow.relations.filter(r=>r!==internal).map(r=>r.relation_id)));
  assert.equal(p.edges.some(e=>e.type==='invented'),false);
});
test('expanded aggregates restore exact original endpoints and internal order links',()=>{
  const p=projectSemanticSwimlanes(workflow,aggregation,new Set(['g2']));
  assert.notEqual(p.nodeForStageId.get('n3'),p.nodeForStageId.get('n4'));
  assert.equal(p.edges.flatMap(e=>e.relation_ids).length,workflow.relations.length);
  assert.equal(p.edges.find(e=>e.type==='REFINES').to,p.nodeForStageId.get('n3'));
  assert.ok(p.units.find(u=>u.id==='g4').y>p.units.find(u=>u.member?.node_id==='n4').y);
});
test('all routed segments avoid cards including expanded and reverse reference links',()=>{
  for(const expanded of [new Set(),new Set(['g2'])]){
    const p=projectSemanticSwimlanes(workflow,aggregation,expanded);
    for(const e of p.edges)for(let i=1;i<e.points.length;i++){
      const a=e.points[i-1],b=e.points[i];assert.ok(a.x===b.x||a.y===b.y);
      for(const u of p.units)assert.equal(segmentHitsRect(a,b,{x:u.x,y:u.y,width:u.width,height:u.height}),false);
    }
  }
});
test('existing stages remain singletons until AI aggregation and ordinary edits are execution',()=>{
  const p=projectSemanticSwimlanes(workflow,null);assert.equal(p.groups.length,6);
  assert.equal(existingStageLane({primary_activity:'Implementation',title:'修改绘图脚本'}),'execution');
  assert.equal(existingStageLane({primary_activity:'Validation',title:'验证均值'}),'execution');
  assert.equal(existingStageLane({primary_activity:'Refinement',title:'纠正口径后重算'}),'revision');
  assert.equal(existingStageLane({primary_activity:'Communication',title:'回应用户问候'}),'input');
});
test('expanded groups in the same lane keep top port escapes outside the aggregate heading',()=>{
  const sameLane=structuredClone(aggregation);sameLane.groups.forEach(g=>g.lane='input');
  const p=projectSemanticSwimlanes(workflow,sameLane,new Set(['g2']));
  assert.equal(p.edges.flatMap(e=>e.relation_ids).length,workflow.relations.length);
  for(const e of p.edges)for(let i=1;i<e.points.length;i++)for(const u of p.units)
    assert.equal(segmentHitsRect(e.points[i-1],e.points[i],{x:u.x,y:u.y,width:u.width,height:u.height}),false);
});
test('imports reject missing coverage, random lanes, hidden semantic endpoints and cross-turn merges',()=>{
  assert.equal(validateSemanticSwimlanes(aggregation,workflow),aggregation);
  for(const change of [v=>v.groups.pop(),v=>v.groups[0].lane='random',v=>v.groups[0].node_ids=['unknown'],v=>v.source_inference_id='stale']){
    const v=structuredClone(aggregation);change(v);assert.throws(()=>validateSemanticSwimlanes(v,workflow));
  }
  const cross=structuredClone(workflow);cross.episodes[3].turn_id='new';assert.throws(()=>validateSemanticSwimlanes(aggregation,cross));
  const hidden=structuredClone(aggregation);hidden.groups[2].node_ids.push('n5');hidden.groups.splice(3,1);assert.throws(()=>validateSemanticSwimlanes(hidden,workflow));
});
