import type { SemanticLane, SemanticNode, SemanticSwimlaneGroup, SemanticSwimlanes, SemanticWorkflow } from '../types/semantic';
import { orthogonalRoute } from './eventRouting.ts';
import type { RoutePoint, RouteRect } from './eventRouting';

export const semanticLanes: Array<{id: SemanticLane; title: string; description: string; color: string; tint: string}> = [
  {id:'input',title:'输入',description:'任务、约束与数据理解',color:'#2563eb',tint:'#eff6ff'},
  {id:'planning',title:'规划',description:'拆解目标、选择方法',color:'#7c3aed',tint:'#f5f3ff'},
  {id:'execution',title:'执行',description:'分析、验证与结果交付',color:'#047857',tint:'#ecfdf5'},
  {id:'revision',title:'修改',description:'反馈、纠错与方案调整',color:'#b45309',tint:'#fffbeb'},
];
export const SWIMLANE_CARD_WIDTH = 300;
export const SWIMLANE_CARD_HEIGHT = 156;
const PITCH = 348;
const MEMBER_HEIGHT = 116;
const MEMBER_GAP = 40;
// Leave enough room for an 18px port escape and the router's 8px card padding.
const GROUP_MEMBER_GAP = 40;

/** Conservative display fallback; it does not claim AI aggregation or invent a plan. */
export function existingStageLane(node: SemanticNode): SemanticLane {
  if (node.primary_activity === 'Refinement') return 'revision';
  if (node.primary_activity === 'Communication' && /问候|询问.*需求|澄清.*范围|确认.*范围/.test(node.title)) return 'input';
  if (['Planning', 'Task Planning'].includes(node.primary_activity) || /^(制定|规划|拆解|确定分析方法|选择分析方法|设计分析方案)/.test(node.title)) return 'planning';
  if (['Task Understanding', 'Data Understanding', 'Exploration'].includes(node.primary_activity)) return 'input';
  return 'execution';
}

export function validateSemanticSwimlanes(value: SemanticSwimlanes, workflow: SemanticWorkflow) {
  const ordered=[...workflow.semantic_nodes].sort((a,b)=>a.sequence-b.sequence||a.node_id.localeCompare(b.node_id));
  if(value.schema_version!=='semantic-swimlanes/0.1'||!value.validation?.valid||value.session_id!==workflow.source_trace.session_id||value.source_inference_id!==workflow.inference_run.inference_id||!Array.isArray(value.groups)) throw new Error('泳道聚合结果不对应当前工作流');
  const ids=value.groups.flatMap(g=>g.node_ids),expected=ordered.map(n=>n.node_id);
  if(ids.length!==expected.length||ids.some((id,i)=>id!==expected[i])||new Set(value.groups.map(g=>g.group_id)).size!==value.groups.length) throw new Error('语义聚合必须按原顺序完整覆盖全部阶段');
  const turns=new Map(workflow.episodes.map(e=>[e.episode_id,e.turn_id]));
  for(const group of value.groups){
    if(!semanticLanes.some(l=>l.id===group.lane)||!group.node_ids.length||!group.group_id||!group.title?.trim()||!group.summary?.trim()||!group.reason?.trim()||!['high','medium','low'].includes(group.confidence)) throw new Error('聚合分类或说明不完整');
    if(group.node_ids.length>1){
      const memberships=group.node_ids.map(id=>new Set(ordered.find(n=>n.node_id===id)!.episode_ids.map(e=>turns.get(e)).filter(Boolean)));
      if(memberships.some(ids=>ids.size!==1)||memberships.some(ids=>[...ids][0]!==[...memberships[0]][0])) throw new Error('不能跨任务或未知轮次聚合');
      if(workflow.relations.some(r=>r.type!=='NEXT'&&group.node_ids.includes(r.from_node_id)&&group.node_ids.includes(r.to_node_id))) throw new Error('不能将语义关系端点隐藏在同一聚合块');
    }
  }
  return value;
}

export interface SwimlaneUnit {
  id: string; group: SemanticSwimlaneGroup; member?: SemanticNode;
  node_ids: string[]; x: number; y: number; width: number; height: number;
}
export interface SwimlaneLink {
  id: string; from: string; to: string; type: string; points: RoutePoint[];
  sourceHandle: string; targetHandle: string; relation_ids: string[];
  evidence_event_ids: string[]; origin: string; confidence: string;
}

export function projectSemanticSwimlanes(workflow: SemanticWorkflow, value: SemanticSwimlanes | null, expanded = new Set<string>()) {
  const ordered=[...workflow.semantic_nodes].sort((a,b)=>a.sequence-b.sequence||a.node_id.localeCompare(b.node_id));
  const stageMap=new Map(ordered.map(n=>[n.node_id,n]));
  const groups: SemanticSwimlaneGroup[]=value?.groups||ordered.map(n=>({group_id:`stage-group-${n.node_id}`,lane:existingStageLane(n),node_ids:[n.node_id],title:n.title,summary:n.summary.value,reason:'按已有阶段活动归类，尚未进行 AI 语义聚合。',confidence:n.confidence.level}));
  const placements:Array<{group:SemanticSwimlaneGroup;lane:number;row:number;height:number}>=[];
  let row=0,previousLane=-1;
  const laneNextRow=[0,0,0,0];
  for(const group of groups){
    const lane=semanticLanes.findIndex(l=>l.id===group.lane);
    // Moving right can share a row. Re-entering this or an earlier lane advances time.
    if(previousLane>=0&&lane<=previousLane)row++;
    row=Math.max(row,laneNextRow[lane]);
    const opened=expanded.has(group.group_id)&&group.node_ids.length>1;
    placements.push({group,lane,row,height:SWIMLANE_CARD_HEIGHT+(opened?GROUP_MEMBER_GAP+group.node_ids.length*(MEMBER_HEIGHT+MEMBER_GAP):0)});
    laneNextRow[lane]=row+1;previousLane=lane;
  }
  const rowHeights:Array<number>=[];
  placements.forEach(p=>{rowHeights[p.row]=Math.max(rowHeights[p.row]||0,p.height);});
  const rowY:Array<number>=[];let height=100;
  rowHeights.forEach((h,i)=>{rowY[i]=height;height+=h+52;});
  const units:SwimlaneUnit[]=[],nodeForStageId=new Map<string,string>();
  for(const p of placements){
    const unit={id:p.group.group_id,group:p.group,node_ids:p.group.node_ids,x:40+p.lane*PITCH,y:rowY[p.row],width:SWIMLANE_CARD_WIDTH,height:SWIMLANE_CARD_HEIGHT};
    units.push(unit);
    if(expanded.has(p.group.group_id)&&p.group.node_ids.length>1){
      p.group.node_ids.forEach((id,i)=>{const member=stageMap.get(id)!;const key=`expanded-${p.group.group_id}-${id}`;
        units.push({...unit,id:key,member,node_ids:[id],y:unit.y+SWIMLANE_CARD_HEIGHT+GROUP_MEMBER_GAP+i*(MEMBER_HEIGHT+MEMBER_GAP),height:MEMBER_HEIGHT});nodeForStageId.set(id,key);
      });
    }else p.group.node_ids.forEach(id=>nodeForStageId.set(id,unit.id));
  }
  const projected=new Map<string,Omit<SwimlaneLink,'points'|'sourceHandle'|'targetHandle'>>();
  for(const relation of workflow.relations){
    const from=nodeForStageId.get(relation.from_node_id),to=nodeForStageId.get(relation.to_node_id);
    if(!from||!to||from===to)continue;
    const key=`${from}|${to}|${relation.type}`,existing=projected.get(key);
    if(existing){existing.relation_ids.push(relation.relation_id);existing.evidence_event_ids=[...new Set([...existing.evidence_event_ids,...relation.evidence_event_ids])];}
    else projected.set(key,{id:`swimlane-edge-${relation.relation_id}`,from,to,type:relation.type,relation_ids:[relation.relation_id],evidence_event_ids:[...relation.evidence_event_ids],origin:relation.origin,confidence:relation.confidence_level});
  }
  const rectangles:RouteRect[]=units.map(u=>({x:u.x,y:u.y,width:u.width,height:u.height}));
  const unitMap=new Map(units.map(u=>[u.id,u]));
  const used:Array<[RoutePoint,RoutePoint]>=[];
  const edges:SwimlaneLink[]=[...projected.values()].map(link=>{
    const a=unitMap.get(link.from)!,b=unitMap.get(link.to)!;
    const sideways=a.x!==b.x;
    const right=b.x>a.x;
    const down=b.y>=a.y;
    const source=sideways?{x:a.x+(right?a.width:0),y:a.y+a.height/2}:{x:a.x+a.width/2,y:a.y+(down?a.height:0)};
    const target=sideways?{x:b.x+(right?0:b.width),y:b.y+b.height/2}:{x:b.x+b.width/2,y:b.y+(down?0:b.height)};
    const escape=sideways?{x:source.x+(right?18:-18),y:source.y}:{x:source.x,y:source.y+(down?18:-18)};
    const enter=sideways?{x:target.x+(right?-18:18),y:target.y}:{x:target.x,y:target.y+(down?-18:18)};
    const preferred=[24, ...semanticLanes.map((_,i)=>40+i*PITCH-24), 40+4*PITCH-24];
    const route=orthogonalRoute(escape,enter,rectangles,preferred,used);
    const points=[source,...route,target];
    for(let i=1;i<points.length;i++)used.push([points[i-1],points[i]]);
    return {...link,points,sourceHandle:`out-${sideways?(right?'right':'left'):(down?'bottom':'top')}`,targetHandle:`in-${sideways?(right?'left':'right'):(down?'top':'bottom')}`};
  });
  return {groups,units,edges,nodeForStageId,width:40+4*PITCH,height:Math.max(420,height+20),lanes:semanticLanes.map((lane,i)=>({...lane,x:24+i*PITCH,width:PITCH-16,count:groups.filter(g=>g.lane===lane.id).length}))};
}

export function swimlaneEdgeLabel(type:string){
  return ({NEXT:'记录顺序',VALIDATES:'验证',REFINES:'修订',RETRY_OF:'重试',USES_RESULT_FROM:'引用结果'} as Record<string,string>)[type]||type;
}
