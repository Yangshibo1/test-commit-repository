import assert from 'node:assert/strict';
import test from 'node:test';
import { layoutEventTurns } from '../frontend/src/utils/eventTurns.ts';
import { mergeEventRelations } from '../frontend/src/utils/eventWorkflow.ts';
import { attachRoutePorts, orthogonalRoute, routeEventRelations, segmentHitsRect, sharedChannelDashOffset } from '../frontend/src/utils/eventRouting.ts';

const trace = { turns: [{ turn_id:'t',prompt_event_id:'a',prompt:'分析任务',event_ids:['a','x','b','y','c','z','d'] }], events:
  ['a','x','b','y','c','z','d'].map((event_id,sequence)=>({event_id,sequence,event_type:event_id==='a'?'user_prompt':'model_response',scope:{turn_id:'t'},payload:{}})),
  relations: ['a-x','x-b','b-y','y-c','c-z','z-d'].map((pair,index)=>({relation_id:`r${index}`,from:pair[0],to:pair[2],type:'result_feeds',origin:'derived'})),
};
const workflow={schema_version:'event-workflow/0.2',event_importance:trace.events.map(e=>({event_id:e.event_id,level:['a','b','c','d'].includes(e.event_id)?'core':'background'})),logical_relations:[
  {relation_id:'long',from:'a',to:'d',type:'SUPPORTS_RESULT',confidence:'high',review_status:'accepted',origin:'inferred',label:'支撑报告'},
  {relation_id:'direct',from:'b',to:'c',type:'LEADS_TO_VALIDATION',confidence:'high',review_status:'accepted',origin:'inferred',label:'验证'},
]};
function geometry(t,w){
  const relations=mergeEventRelations(t,w).relations,layout=layoutEventTurns(t,w,relations,true);
  const rectangles=t.events.map(e=>{const turn=layout.turns.find(t=>t.id===layout.eventToTurn.get(e.event_id)),p=layout.positions.get(e.event_id),s=layout.sizes.get(e.event_id);return {x:turn.x+p.x,y:turn.y+p.y,width:s.width,height:s.height};});
  return {relations,layout,rectangles,routes:routeEventRelations(layout,t.events,relations,w)};
}
function assertClear(points,rectangles){
  for(let i=1;i<points.length;i++) {
    const a=points[i-1],b=points[i];assert.ok(a.x===b.x||a.y===b.y,'every segment is orthogonal');
    for(const rect of rectangles)assert.equal(segmentHitsRect(a,b,rect),false,'path must not cross a card interior');
  }
}
test('key nodes use the left spine and auxiliary nodes extend right without overlapping',()=>{
  const {layout,rectangles}=geometry(trace,workflow),turn=layout.turns[0];
  for(const e of trace.events){const p=layout.positions.get(e.event_id),s=layout.sizes.get(e.event_id),center=p.x+s.width/2;
    if(['a','b','c','d'].includes(e.event_id))assert.equal(center,turn.centerX);
    else assert.ok(Math.abs(center-turn.centerX)>turn.primaryExtent);
    assert.deepEqual(Object.keys(s).sort(),['height','width'],'Dagre must not mutate the public size map');
  }
  const side=trace.events.filter(e=>['x','y','z'].includes(e.event_id)).map(e=>layout.positions.get(e.event_id).x+layout.sizes.get(e.event_id).width/2-turn.centerX);
  assert.ok(side.every(x=>x>0));
  for(let i=0;i<rectangles.length;i++)for(let j=i+1;j<rectangles.length;j++){
    const a=rectangles[i],b=rectangles[j];assert.equal(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y,false);
  }
});
test('decisions, turning points and results share the central spine; normal execution uses the sides',()=>{
  const roles={a:'key_decision',b:'key_turning_point',c:'key_result',d:'key_result'};
  const w={...workflow,schema_version:'event-workflow/0.3',event_importance:trace.events.map(e=>({event_id:e.event_id,level:roles[e.event_id]||'normal_execution'}))};
  const {layout,routes,rectangles}=geometry(trace,w),turn=layout.turns[0];
  for(const e of trace.events){const x=layout.positions.get(e.event_id).x+layout.sizes.get(e.event_id).width/2;
    if(roles[e.event_id]) assert.equal(x,turn.centerX);
    else assert.ok(Math.abs(x-turn.centerX)>turn.primaryExtent);
  }
  for(const route of routes.values())assertClear(route.points,rectangles);
  assert.equal(routes.get('long').primary,true);
  assert.equal(routes.get('r0').primary,false);
});
test('primary shortcuts avoid intermediate core cards; auxiliary edges use short clear paths',()=>{
  const {routes,rectangles,relations,layout}=geometry(trace,workflow);
  assert.equal(routes.size,relations.length);
  for(const route of routes.values())assertClear(route.points,rectangles);
  assert.equal(routes.get('long').primary,true);
  assert.ok(routes.get('long').points.length>2,'a shortcut cannot go through intermediate core nodes');
  const auxiliary=routes.get('r0');assert.equal(auxiliary.primary,false);assert.equal(auxiliary.sourceHandle,'main-out');
  const turn=layout.turns[0],local=rectangles;
  const minX=Math.min(auxiliary.points[0].x,auxiliary.points.at(-1).x),maxX=Math.max(auxiliary.points[0].x,auxiliary.points.at(-1).x);
  assert.ok(auxiliary.points.every(p=>p.x>=minX&&p.x<=maxX),'a clear gap must not use outside tracks');
  assert.equal(layout.turns[0].y,turn.y);
});
test('visibility routing works with negative coordinates and an out-of-range preferred domain',()=>{
  const obstacles=[{x:-80,y:40,width:100,height:140}];
  const start={x:-30,y:0},end={x:-30,y:240};
  const route=orthogonalRoute(start,end,obstacles,[0],[],[100,200]);
  assert.deepEqual(route[0],start);assert.deepEqual(route.at(-1),end);assertClear(route,obstacles);
});
test('cross-Turn links preserve topology and avoid cards without moving either Turn',()=>{
  const source={...trace,events:[...trace.events,{event_id:'next',sequence:10,event_type:'user_prompt',scope:{turn_id:'next'},payload:{content:'下一任务'}}],turns:[...trace.turns,{turn_id:'next',prompt_event_id:'next',prompt:'下一任务',event_ids:['next']}]};
  const w={...workflow,event_importance:[...workflow.event_importance,{event_id:'next',level:'core'}],logical_relations:[...workflow.logical_relations,{relation_id:'cross',from:'d',to:'next',type:'GUIDES_METHOD',confidence:'high',review_status:'accepted',origin:'inferred',label:'指导'}]};
  const g=geometry(source,w);assertClear(g.routes.get('cross').points,g.rectangles);
  assert.equal(g.layout.turns[0].y,g.layout.turns[1].y);
});
test('labels are outside cards and do not overlap other primary labels',()=>{
  const {routes,rectangles}=geometry(trace,workflow),boxes=[];
  for(const route of routes.values())if(route.labelPosition){const p=route.labelPosition,box={x:p.x-42,y:p.y-12,width:84,height:24};
    const overlap=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
    assert.ok(!rectangles.some(r=>overlap(box,r)));assert.ok(!boxes.some(r=>overlap(box,r)));boxes.push(box);
  }
  assert.ok(boxes.length>0);
});
test('a Turn with no AI result remains fully routable',()=>{
  const g=geometry(trace,null);assert.equal(g.routes.size,g.relations.length);
  for(const route of g.routes.values())assertClear(route.points,g.rectangles);
});
test('measured handle offsets keep every rendered segment orthogonal',()=>{
  for(const points of [[{x:0,y:0},{x:0,y:100}], [{x:0,y:0},{x:0,y:14},{x:50,y:14},{x:50,y:86},{x:0,y:86},{x:0,y:100}]]) {
    const start={x:2.5,y:0},end={x:1.5,y:100},attached=attachRoutePorts(points,start,end);
    assert.deepEqual(attached[0],start);assert.deepEqual(attached.at(-1),end);assertClear(attached,[]);
  }
});
test('collinear escape points attach as one straight segment at the actual card center',()=>{
  const vertical=[{x:190,y:256},{x:190,y:274},{x:190,y:290},{x:190,y:308}];
  assert.deepEqual(attachRoutePorts(vertical,{x:191.5,y:259},{x:191.5,y:301}),[{x:191.5,y:259},{x:191.5,y:301}]);
  const horizontal=[{x:340,y:178},{x:358,y:178},{x:370,y:178},{x:388,y:178}];
  assert.deepEqual(attachRoutePorts(horizontal,{x:343,y:179.5},{x:385,y:179.5}),[{x:343,y:179.5},{x:385,y:179.5}]);
  assert.deepEqual(attachRoutePorts(vertical,{x:191.5000001,y:259},{x:191.4999999,y:301}),[{x:191.5,y:259},{x:191.5,y:301}]);
});
test('port adjustments preserve the original detour without extra centerline stubs',()=>{
  const planned=[{x:0,y:0},{x:0,y:14},{x:50,y:14},{x:50,y:86},{x:0,y:86},{x:0,y:100}];
  const actual=attachRoutePorts(planned,{x:1.5,y:3},{x:1.5,y:97});
  assert.deepEqual(actual,[{x:1.5,y:3},{x:1.5,y:14},{x:50,y:14},{x:50,y:86},{x:1.5,y:86},{x:1.5,y:97}]);
  assertClear(actual,[{x:15,y:30,width:20,height:40}]);
  const horizontal=[{x:0,y:0},{x:14,y:0},{x:14,y:50},{x:86,y:50},{x:86,y:0},{x:100,y:0}];
  const h=attachRoutePorts(horizontal,{x:3,y:1.5},{x:97,y:1.5});
  assert.deepEqual(h,[{x:3,y:1.5},{x:14,y:1.5},{x:14,y:50},{x:86,y:50},{x:86,y:1.5},{x:97,y:1.5}]);
  assertClear(h,[{x:30,y:15,width:40,height:20}]);
});
test('parallel key branches start from the left spine and stay apart',()=>{
  const source={turns:[{turn_id:'t',prompt_event_id:'a',prompt:'分支任务',event_ids:['a','b','c','d']}],events:['a','b','c','d'].map((event_id,sequence)=>({event_id,sequence,event_type:'model_response',scope:{turn_id:'t'},payload:{}})),relations:[['a','b'],['a','c'],['b','d'],['c','d']].map(([from,to],index)=>({relation_id:'fork'+index,from,to,type:'invokes',origin:'derived'}))};
  const w={event_importance:source.events.map(e=>({event_id:e.event_id,level:'core'})),logical_relations:[]};
  const g=geometry(source,w),l=g.layout,center=l.turns[0].centerX;
  const bx=l.positions.get('b').x+l.sizes.get('b').width/2,cx=l.positions.get('c').x+l.sizes.get('c').width/2;
  assert.equal(Math.min(bx,cx),center);assert.ok(bx!==cx);assert.ok(bx>=center&&cx>=center);
  for(const route of g.routes.values())assertClear(route.points,g.rectangles);
});

test('an unobstructed straight trunk stays straight even when another relation shares it',()=>{
  const start={x:100,y:20},end={x:100,y:220};
  assert.deepEqual(orthogonalRoute(start,end,[],[],[[start,end]]),[start,end]);
});
test('an unobstructed branch uses two balanced elbows instead of a stair-step path',()=>{
  const route=orthogonalRoute({x:0,y:0},{x:200,y:160},[]);
  assert.equal(route.length,4);assertClear(route,[]);
  assert.deepEqual(route[1],{x:0,y:80});
  assert.deepEqual(route[2],{x:200,y:80});
});
test('routing expands its search when a tall neighbor blocks the local horizontal corridor',()=>{
  const obstacle={x:60,y:-150,width:80,height:300};
  const path=orthogonalRoute({x:0,y:0},{x:200,y:0},[obstacle]);
  assertClear(path,[obstacle]);
  assert.ok(path.some(p=>Math.abs(p.y)>=158));
});
test('concatenated peripheral paths remove overshoot and retracing at rail junctions',()=>{
  const start={x:0,y:0},end={x:50,y:180};
  const planned=[start,{x:120,y:0},{x:120,y:200},{x:120,y:160},{x:66,y:160},{x:66,y:180},end];
  const attached=attachRoutePorts(planned,start,end);
  assert.deepEqual(attached,[start,{x:120,y:0},{x:120,y:160},{x:66,y:160},{x:66,y:180},end]);
  assertClear(attached,[{x:30,y:30,width:70,height:100}]);
});
test('aligned auxiliary neighbors connect directly without a perimeter excursion',()=>{
  const t={turns:[{turn_id:'t',prompt_event_id:'a',event_ids:['a','b']}],events:['a','b'].map((event_id,sequence)=>({event_id,sequence,event_type:'model_response',scope:{turn_id:'t'},payload:{}})),relations:[{relation_id:'plain',from:'a',to:'b',type:'result_feeds',origin:'derived'}]};
  const g=geometry(t,null),r=g.routes.get('plain');
  assert.equal(r.primary,false);assert.equal(r.points.length,2);
  assert.equal(r.sourceHandle,'main-out');assertClear(r.points,g.rectangles);
});
test('routes stay in their Turn with downward centered attachments',()=>{
  const g=geometry(trace,workflow),turn=g.layout.turns[0];
  for(const route of g.routes.values()) {
    assertClear(route.points,g.rectangles);
    for(const p of route.points)assert.ok(p.x>=turn.x && p.x<=turn.x+turn.width);
    for(let i=2;i<route.points.length;i++) {
      const [a,b,c]=route.points.slice(i-2,i+1);
      assert.ok(!(a.x===b.x&&b.x===c.x),'no redundant vertical elbow');
      assert.ok(!(a.y===b.y&&b.y===c.y),'no redundant horizontal elbow');
    }
    {
      assert.equal(route.points[0].x,route.points[1].x);
      assert.ok(route.points[1].y>route.points[0].y);
      assert.equal(route.points.at(-1).x,route.points.at(-2).x);
      assert.ok(route.points.at(-1).y>route.points.at(-2).y);
    }
  }
});
test('cross-Turn relations also connect bottom center to top center',()=>{
  const t={turns:[{turn_id:'one',event_ids:['a']},{turn_id:'two',event_ids:['b']}],events:[{event_id:'a',sequence:1,scope:{turn_id:'one'},payload:{}},{event_id:'b',sequence:2,scope:{turn_id:'two'},payload:{}}],relations:[{relation_id:'across',from:'a',to:'b',type:'result_feeds',origin:'derived'}]};
  const g=geometry(t,null),r=g.routes.get('across');
  assert.equal(r.sourceHandle,'main-out');assert.equal(r.targetHandle,'main-in');
  assert.ok(r.points.length>2);assertClear(r.points,g.rectangles);
  assert.equal(r.points[0].x,r.points[1].x);assert.ok(r.points[1].y>r.points[0].y);
  assert.equal(r.points.at(-1).x,r.points.at(-2).x);assert.ok(r.points.at(-1).y>r.points.at(-2).y);
});

 test('every relation attaches to exact bottom and top midpoints regardless of importance',()=>{
  for(const w of [workflow,null]) {
    const g=geometry(trace,w);
    for(const relation of g.relations) {
      const r=g.routes.get(relation.relation_id);
      const from=g.rectangles[trace.events.findIndex(e=>e.event_id===relation.from)];
      const to=g.rectangles[trace.events.findIndex(e=>e.event_id===relation.to)];
      assert.deepEqual(r.points[0],{x:from.x+from.width/2,y:from.y+from.height});
      assert.deepEqual(r.points.at(-1),{x:to.x+to.width/2,y:to.y});
      assert.equal(r.sourceHandle,'main-out');assert.equal(r.targetHandle,'main-in');
    }
  }
});

test('offset auxiliary neighbors use the gap between cards, even with a wider unrelated branch',()=>{
  const t={events:[{event_id:'a',sequence:1},{event_id:'b',sequence:2},{event_id:'far',sequence:3}]};
  const l={turns:[{id:'t',x:0,y:0,width:1800,centerX:900,primaryExtent:150,events:t.events}],
    eventToTurn:new Map(t.events.map(e=>[e.event_id,'t'])),primaryEventIds:new Set(),
    positions:new Map([['a',{x:1200,y:0}],['b',{x:900,y:220}],['far',{x:40,y:600}]]),
    sizes:new Map(t.events.map(e=>[e.event_id,{width:200,height:100}]))};
  const relation={relation_id:'gap',from:'a',to:'b',kind:'rule',type:'result_feeds'};
  const points=routeEventRelations(l,t.events,[relation],null).get('gap').points;
  assert.equal(points.length,4,'only two elbows are needed');
  assert.deepEqual(points[0],{x:1300,y:100});assert.deepEqual(points.at(-1),{x:1000,y:220});
  assert.ok(points.every(p=>p.x>=1000&&p.x<=1300),'do not force a left or right perimeter trip');
  const length=points.slice(1).reduce((sum,p,i)=>sum+Math.abs(p.x-points[i].x)+Math.abs(p.y-points[i].y),0);
  assert.equal(length,420,'clear route has exactly Manhattan length');
});
test('shared branch segments do not force a higher-bend route across an empty gap',()=>{
  const start={x:0,y:0},end={x:200,y:160};
  assert.deepEqual(orthogonalRoute(start,end,[],[],[[start,{x:0,y:80}],[{x:0,y:80},{x:200,y:80}]]),
    [start,{x:0,y:80},{x:200,y:80},end]);
});

function sharedFixture(merge=false,obstacle=false) {
  const boxes=merge ? [
    ['a',{x:0,y:0,width:100,height:100}],['b',{x:200,y:10,width:100,height:80}],['c',{x:400,y:300,width:100,height:100}],
  ] : [
    ['a',{x:400,y:0,width:100,height:100}],['b',{x:0,y:240,width:100,height:120}],['c',{x:150,y:260,width:100,height:80}],
  ];
  if(obstacle)boxes.push(['block',{x:280,y:110,width:60,height:180}]);
  const events=boxes.map(([event_id],sequence)=>({event_id,sequence}));
  const l={turns:[{id:'t',x:0,y:0,width:700,centerX:350,primaryExtent:100,events}],eventToTurn:new Map(events.map(e=>[e.event_id,'t'])),primaryEventIds:new Set(),
    positions:new Map(boxes.map(([id,r])=>[id,{x:r.x,y:r.y}])),sizes:new Map(boxes.map(([id,r])=>[id,{width:r.width,height:r.height}]))};
  const relations=(merge?[['a','c'],['b','c']]:[['a','b'],['a','c']]).map(([from,to],i)=>({relation_id:`r${i}`,from,to,kind:'rule',type:'result_feeds'}));
  return {events,l,relations,rectangles:boxes.map(([,r])=>r),routes:routeEventRelations(l,events,relations,null)};
}
test('same-source branches with unequal target heights share a clear horizontal bus',()=>{
  const g=sharedFixture(),routes=[...g.routes.values()];
  assert.equal(routes[0].sharedChannelY,170);assert.equal(routes[1].sharedChannelY,170);
  assert.equal(g.routes.size,2,'relations remain individually addressable');
  for(const r of routes){assertClear(r.points,g.rectangles);assert.equal(r.points.length,4);assert.equal(r.sourceHandle,'main-out');assert.equal(r.targetHandle,'main-in');}
  const reversed=routeEventRelations(g.l,g.events,[...g.relations].reverse(),null);
  for(const [id,r] of g.routes)assert.deepEqual(reversed.get(id),r,'input order must not change routing');
});
test('same-target merges share a bus without changing their true sources',()=>{
  const g=sharedFixture(true),routes=[...g.routes.values()];
  assert.equal(routes[0].sharedChannelY,200);assert.equal(routes[1].sharedChannelY,200);
  assert.notEqual(routes[0].points[0].x,routes[1].points[0].x);
  for(const r of routes)assertClear(r.points,g.rectangles);
});
test('blocked sharing falls back to obstacle routing instead of crossing a card',()=>{
  const g=sharedFixture(false,true);
  for(const r of g.routes.values()){assert.equal(r.sharedChannelY,undefined);assertClear(r.points,g.rectangles);}
});
test('different relationship styles are not bundled together',()=>{
  const g=sharedFixture();g.relations[1]={...g.relations[1],kind:'logical'};
  const routes=routeEventRelations(g.l,g.events,g.relations,null);
  for(const r of routes.values())assert.equal(r.sharedChannelY,undefined);
});

test('shared dashed buses keep the same dash phase despite different stems or direction',()=>{
  const y=200;
  const paths=[
    [{x:10,y:0},{x:10,y},{x:250,y},{x:250,y:300}],
    [{x:80,y:40},{x:80,y},{x:250,y},{x:250,y:300}],
    [{x:250,y:20},{x:250,y},{x:10,y},{x:10,y:300}],
  ];
  const mod=n=>((n%10)+10)%10;
  for(const x of [100.5,104.5,107.5,113.5,128.5,150.5]){
    const painted=paths.map(points=>{
      const distanceToX=y-points[0].y+Math.abs(x-points[1].x);
      return mod(distanceToX+sharedChannelDashOffset(points,y))<6;
    });
    assert.ok(painted.every(value=>value===painted[0]),'overlapping dashed lines must not fill each other’s gaps');
  }
});

function lateralFixture(){
 const boxes=[['a',{x:300,y:0,width:160,height:100}],['b',{x:300,y:350,width:160,height:100}],['c1',{x:0,y:200,width:200,height:100}],['c2',{x:0,y:500,width:200,height:100}]];
 const events=boxes.map(([event_id],sequence)=>({event_id,sequence}));
 const layout={turns:[{id:'t',x:0,y:0,width:650,centerX:100,primaryExtent:100,events}],eventToTurn:new Map(events.map(e=>[e.event_id,'t'])),primaryEventIds:new Set(['c1','c2']),positions:new Map(boxes.map(([id,r])=>[id,{x:r.x,y:r.y}])),sizes:new Map(boxes.map(([id,r])=>[id,{width:r.width,height:r.height}]))};
 const workflow={event_importance:events.map(e=>({event_id:e.event_id,level:e.event_id.startsWith('c')?'key_result':'normal_execution'}))};
 const relations=[['a','c1','PROVIDES_INPUT'],['a','c2','SUPPORTS_RESULT'],['b','c2','GUIDES_METHOD']].map(([from,to,type],i)=>({relation_id:`side${i}`,from,to,type,kind:'logical',confidence:'high'}));
 return {boxes,events,layout,workflow,relations,routes:routeEventRelations(layout,events,relations,workflow)};
}
test('fewer bends allow mixed bottom-to-right ports while keeping logical branches individually addressable',()=>{
 const g=lateralFixture(),[r1,r2,r3]=['side0','side1','side2'].map(id=>g.routes.get(id));
 for(const route of g.routes.values())assertClear(route.points,g.boxes.map(([,r])=>r));
 assert.equal(r1.sourceHandle,'main-out');assert.equal(r1.targetHandle,'lateral-in-right');
 assert.equal(r1.points.length,3,'one bend instead of two with bottom-to-top ports');
 assert.equal(r3.sourceHandle,'main-out');assert.equal(r3.targetHandle,'lateral-in-right');
 assert.deepEqual(r2.points.at(-1),r3.points.at(-1),'the true target port remains shared');
 assert.equal(g.routes.size,3,'port optimization must not combine or discard relation identities');
 const reversed=routeEventRelations(g.layout,g.events,[...g.relations].reverse(),g.workflow);
 for(const [id,route] of g.routes)assert.deepEqual(reversed.get(id),route,'relation input order must not change the chosen ports');
});
test('a core right-to-top shortcut is chosen only when it removes a bend, with measured ports staying orthogonal',()=>{
 const g=lateralFixture();
 const relation={relation_id:'out',from:'c1',to:'b',type:'GUIDES_METHOD',kind:'logical',confidence:'high'};
 const route=routeEventRelations(g.layout,g.events,[relation],g.workflow).get('out');
 assert.equal(route.sourceHandle,'lateral-out-right');assert.equal(route.targetHandle,'main-in');
 assert.equal(route.points.length,3);
 assertClear(route.points,g.boxes.map(([,r])=>r));
 const actual=attachRoutePorts(route.points,{x:202,y:251.5},{x:381,y:348});
 assertClear(actual,[]);assert.equal(actual[0].y,actual[1].y);assert.equal(actual.at(-1).x,actual.at(-2).x);
});
test('equal-bend side routes keep the default bottom-to-top ports even if the side route is shorter',()=>{
 const g=lateralFixture();
 g.events.push({event_id:'block',sequence:5});g.layout.eventToTurn.set('block','t');g.layout.positions.set('block',{x:350,y:210});g.layout.sizes.set('block',{width:60,height:40});
 const route=routeEventRelations(g.layout,g.events,[g.relations[0]],g.workflow).get('side0');
 assert.equal(route.sourceHandle,'main-out');assert.equal(route.targetHandle,'main-in');
 assert.equal(route.points.length,4);
 assertClear(route.points,[...g.boxes.map(([,r])=>r),{x:350,y:210,width:60,height:40}]);
});
test('a simpler side shortcut is rejected when it crosses an unrelated relation',()=>{
 const g=lateralFixture();
 for(const [id,x,y] of [['u',240,125],['v',430,245]]){
  g.events.push({event_id:id,sequence:8});g.layout.eventToTurn.set(id,'t');g.layout.positions.set(id,{x,y});g.layout.sizes.set(id,{width:20,height:20});
 }
 const relations=[g.relations[0],{relation_id:'other',from:'u',to:'v',kind:'rule',type:'result_feeds'}];
 const routes=routeEventRelations(g.layout,g.events,relations,g.workflow);
 assert.equal(routes.get('side0').sourceHandle,'main-out');assert.equal(routes.get('side0').targetHandle,'main-in');
 for(const route of routes.values())assertClear(route.points,[...g.boxes.map(([,r])=>r),{x:240,y:125,width:20,height:20},{x:430,y:245,width:20,height:20}]);
});
test('same-height logical side ports connect in one straight segment',()=>{
 const g=lateralFixture();g.layout.positions.set('b',{x:300,y:200});
 const route=routeEventRelations(g.layout,g.events,[{relation_id:'straight',from:'c1',to:'b',kind:'logical',confidence:'high'}],g.workflow).get('straight');
 assert.deepEqual(route.points,[{x:200,y:250},{x:300,y:250}]);
});
test('nearby logical horizontal segments share one clear bus even with different labels and target rows',()=>{
 const events=['a','b','c'].map((event_id,sequence)=>({event_id,sequence}));
 const boxes=[{x:0,y:0,width:100,height:100},{x:200,y:240,width:100,height:100},{x:300,y:260,width:100,height:100}];
 const layout={turns:[{id:'t',x:0,y:0,width:600,centerX:50,primaryExtent:50,events}],eventToTurn:new Map(events.map(e=>[e.event_id,'t'])),primaryEventIds:new Set(),positions:new Map(events.map((e,i)=>[e.event_id,boxes[i]])),sizes:new Map(events.map(e=>[e.event_id,{width:100,height:100}]))};
 const relations=[{relation_id:'r1',from:'a',to:'b',type:'PROVIDES_INPUT',kind:'logical'},{relation_id:'r2',from:'a',to:'c',type:'SUPPORTS_RESULT',kind:'logical'}];
 const routes=routeEventRelations(layout,events,relations,null);
 const [r1,r2]=[...routes.values()];
 assert.equal(r1.sharedChannelY,r2.sharedChannelY);assert.equal(r1.sharedChannelY,170);
 assert.equal(r1.points[1].y,r2.points[1].y);
 for(const r of routes.values()){assertClear(r.points,boxes);assert.equal(r.points.length,4);}
});
test('lateral shortcuts fall back to obstacle avoidance instead of passing through another branch',()=>{
 const g=lateralFixture();
 g.events.push({event_id:'block',sequence:5});g.layout.eventToTurn.set('block','t');g.layout.positions.set('block',{x:230,y:160});g.layout.sizes.set('block',{width:50,height:280});
 const routes=routeEventRelations(g.layout,g.events,[{relation_id:'blocked',from:'c1',to:'b',type:'GUIDES_METHOD',kind:'logical',confidence:'high'}],g.workflow);
 assertClear(routes.get('blocked').points,[...g.boxes.map(([,r])=>r),{x:230,y:160,width:50,height:280}]);
});

function heightAlignmentFixture({mirror=false,blocked=false,unrelated=false}={}) {
 const boxes=[['a',{x:100,y:0,width:100,height:100}],['middle',{x:100,y:180,width:100,height:100}],['b',{x:400,y:320,width:100,height:100}],['c',{x:100,y:500,width:100,height:100}]];
 if(blocked)boxes.push(['block',{x:110,y:445,width:20,height:25}]);
 // Keep the long outgoing arm on the opposite side of the dashed branch.
 if(mirror)boxes.push(['rightblock',{x:205,y:180,width:80,height:100}]);
 if(mirror)for(const [,box] of boxes)box.y=600-box.y-box.height;
 const events=boxes.map(([event_id],sequence)=>({event_id,sequence}));
 const layout={turns:[{id:'t',x:0,y:0,width:650,centerX:150,primaryExtent:50,events}],eventToTurn:new Map(events.map(e=>[e.event_id,'t'])),primaryEventIds:new Set(['a','c']),positions:new Map(boxes.map(([id,r])=>[id,{x:r.x,y:r.y}])),sizes:new Map(boxes.map(([id,r])=>[id,{width:r.width,height:r.height}]))};
 const relations=[{relation_id:'logic',from:'a',to:'c',kind:'logical',type:'SUPPORTS_RESULT',confidence:'high'},
  {relation_id:'dash',from:'b',to:unrelated?'middle':'c',kind:'rule',type:'result_feeds'}];
 if(mirror)for(const r of relations)[r.from,r.to]=[r.to,r.from];
 return {boxes,events,layout,relations,routes:routeEventRelations(layout,events,relations,null)};
}
const interiorHorizontalHeights=route=>route.points.slice(1).flatMap((p,i)=>i>0&&i+1<route.points.length-1&&p.y===route.points[i].y?[p.y]:[]);
test('solid logical and dashed incoming arms meet at the same height without combining their styles or identities',()=>{
 const g=heightAlignmentFixture(),logic=g.routes.get('logic'),dash=g.routes.get('dash');
 assert.equal(interiorHorizontalHeights(logic).at(-1),460);assert.equal(interiorHorizontalHeights(dash).at(-1),460);
 assert.equal(logic.primary,true);assert.equal(dash.primary,false);assert.equal(logic.points.length,6);assert.equal(dash.points.length,4);
 assert.equal(logic.targetHandle,'main-in');assert.equal(dash.targetHandle,'main-in');
 assert.deepEqual(logic.points.at(-1),{x:150,y:500});assert.deepEqual(dash.points.at(-1),{x:150,y:500});
 for(const route of g.routes.values())assertClear(route.points,g.boxes.map(([,r])=>r));
 const reversed=routeEventRelations(g.layout,g.events,[...g.relations].reverse(),null);
 for(const [id,route] of g.routes)assert.deepEqual(reversed.get(id),route);
});
test('solid and dashed outgoing arms also share a height at their common source',()=>{
 const g=heightAlignmentFixture({mirror:true});
 assert.equal(interiorHorizontalHeights(g.routes.get('logic'))[0],140);
 assert.equal(interiorHorizontalHeights(g.routes.get('dash'))[0],140);
 for(const route of g.routes.values())assertClear(route.points,g.boxes.map(([,r])=>r));
});
test('horizontal height alignment is skipped when the dashed height would cross a card',()=>{
 const g=heightAlignmentFixture({blocked:true});
 assert.notEqual(interiorHorizontalHeights(g.routes.get('logic')).at(-1),interiorHorizontalHeights(g.routes.get('dash')).at(-1));
 for(const route of g.routes.values())assertClear(route.points,g.boxes.map(([,r])=>r));
});
test('unrelated dashed paths do not pull logical horizontal segments to another height',()=>{
 const g=heightAlignmentFixture({unrelated:true});
 assert.equal(interiorHorizontalHeights(g.routes.get('logic')).at(-1),486);
 for(const route of g.routes.values())assertClear(route.points,g.boxes.map(([,r])=>r));
});
