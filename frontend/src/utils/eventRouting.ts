import type { ObserverEvent } from '../types/observer';
import type { EventWorkflow } from '../types/eventWorkflow';
import type { DisplayEventRelation } from './eventWorkflow';
import { isKeyEvent, isRoutineEvent } from './eventWorkflow.ts';
import type { layoutEventTurns } from './eventTurns';

export interface RoutePoint { x: number; y: number }
export interface RouteRect { x: number; y: number; width: number; height: number }
export interface EventEdgeRoute {
  primary: boolean; points: RoutePoint[]; sourceHandle: string; targetHandle: string;
  labelPosition?: RoutePoint; sharedChannelY?: number;
}
type Segment = [RoutePoint, RoutePoint];
const round = (value: number) => Math.round(value * 1000) / 1000;
const unique = (values: number[]) => [...new Set(values.map(round))].sort((a, b) => a - b);
const inflate = (rect: RouteRect, padding: number): RouteRect => ({ x: rect.x - padding, y: rect.y - padding, width: rect.width + padding * 2, height: rect.height + padding * 2 });
const distance = (a: RoutePoint, b: RoutePoint) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);

export function segmentHitsRect(a: RoutePoint, b: RoutePoint, r: RouteRect) {
  if (Math.abs(a.x - b.x) < .001) return a.x > r.x + .001 && a.x < r.x + r.width - .001 && Math.max(a.y, b.y) > r.y + .001 && Math.min(a.y, b.y) < r.y + r.height - .001;
  if (Math.abs(a.y - b.y) < .001) return a.y > r.y + .001 && a.y < r.y + r.height - .001 && Math.max(a.x, b.x) > r.x + .001 && Math.min(a.x, b.x) < r.x + r.width - .001;
  return true;
}
function overlaps(a: RouteRect, b: RouteRect) { return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y; }
function simplify(points: RoutePoint[]) {
  const result: RoutePoint[] = [];
  for (const raw of points) {
    const p = { x: round(raw.x), y: round(raw.y) };
    if (result.length && distance(result[result.length - 1], p) < .001) continue;
    while (result.length >= 2) {
      const a = result[result.length - 2], b = result[result.length - 1];
      const sameX = a.x === b.x && b.x === p.x;
      const sameY = a.y === b.y && b.y === p.y;
      if (!sameX && !sameY) break;
      result.pop();
    }
    if (!result.length || distance(result[result.length - 1], p) >= .001) result.push(p);
  }
  return result;
}
/** Measured React Flow handles can differ a few pixels from CSS card bounds. */
export function attachRoutePorts(points: RoutePoint[], start: RoutePoint, end: RoutePoint) {
  const route = simplify(points);
  start = {x:round(start.x), y:round(start.y)};
  end = {x:round(end.x), y:round(end.y)};
  if (route.length < 2) return simplify([start, end]);
  // Collapse collinear escape points before attaching measured handles. Keeping
  // the old centerline creates a tiny out-and-back detour on an otherwise straight edge.
  if (route.length === 2 && route[0].x === route[1].x) {
    const y = (start.y + end.y) / 2;
    return simplify([start, {x:start.x,y}, {x:end.x,y}, end]);
  }
  if (route.length === 2 && route[0].y === route[1].y) {
    const x = (start.x + end.x) / 2;
    return simplify([start, {x,y:start.y}, {x,y:end.y}, end]);
  }
  const firstVertical = route[0].x === route[1].x;
  const lastVertical = route[route.length-2].x === route[route.length-1].x;
  // Move the existing end bends with their ports, keeping the intended detour
  // and its perpendicular segments instead of adding extra adjustment bends.
  route[1][firstVertical ? 'x' : 'y'] = start[firstVertical ? 'x' : 'y'];
  route[route.length-2][lastVertical ? 'x' : 'y'] = end[lastVertical ? 'x' : 'y'];
  route[0] = start;
  route[route.length-1] = end;
  return simplify(route);
}
function overlapCost(a: RoutePoint, b: RoutePoint, used: Segment[]) {
  let cost = 0;
  for (const [c, d] of used) {
    if (a.x === b.x && c.x === d.x && a.x === c.x) cost += Math.max(0, Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) - Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y))) * 2;
    else if (a.y === b.y && c.y === d.y && a.y === c.y) cost += Math.max(0, Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) - Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x))) * 2;
    else {
      const h = a.y === b.y ? [a, b] : [c, d], v = a.y === b.y ? [c, d] : [a, b];
      if (h[0].y === h[1].y && v[0].x === v[1].x && v[0].x > Math.min(h[0].x, h[1].x) && v[0].x < Math.max(h[0].x, h[1].x) && h[0].y > Math.min(v[0].y, v[1].y) && h[0].y < Math.max(v[0].y, v[1].y)) cost += 28;
    }
  }
  return cost;
}

class Queue {
  private items: Array<{id: number; score: number}> = [];
  get length() { return this.items.length; }
  push(item: {id: number; score: number}) {
    this.items.push(item); let i = this.items.length - 1;
    while (i) { const parent = (i - 1) >> 1; if (this.items[parent].score <= item.score) break; this.items[i] = this.items[parent]; i = parent; } this.items[i] = item;
  }
  pop() {
    const first = this.items[0], last = this.items.pop()!;
    if (this.items.length) {
      let i = 0;
      while (i * 2 + 1 < this.items.length) { let child = i * 2 + 1; if (child + 1 < this.items.length && this.items[child + 1].score < this.items[child].score) child++; if (last.score <= this.items[child].score) break; this.items[i] = this.items[child]; i = child; } this.items[i] = last;
    }
    return first;
  }
}

/** Orthogonal visibility-grid search. Card interiors are hard obstacles. */
export function orthogonalRoute(start: RoutePoint, end: RoutePoint, rectangles: RouteRect[], preferredX: number[] = [], used: Segment[] = [], xBounds?: [number, number], expanded = false): RoutePoint[] {
  const bounds = {
    left: xBounds?.[0] ?? Math.min(start.x, end.x, ...rectangles.map(r => r.x)) - 24,
    right: xBounds?.[1] ?? Math.max(start.x, end.x, ...rectangles.map(r => r.x + r.width)) + 24,
    top: expanded ? Math.min(start.y, end.y, ...rectangles.map(r => r.y)) - 24 : Math.min(start.y, end.y) - 80,
    bottom: expanded ? Math.max(start.y, end.y, ...rectangles.map(r => r.y + r.height)) + 24 : Math.max(start.y, end.y) + 80,
  };
  const obstacles = rectangles.map(r => inflate(r, 8)).filter(r => r.x < bounds.right && r.x + r.width > bounds.left && r.y < bounds.bottom && r.y + r.height > bounds.top);
  const clear = (points: RoutePoint[]) => points.every(p => p.x >= bounds.left && p.x <= bounds.right) &&
    points.slice(1).every((p, i) => !obstacles.some(r => segmentHitsRect(points[i], p, r)));
  const direct = simplify([start, end]);
  if ((start.x === end.x || start.y === end.y) && clear(direct)) return direct;
  // Try one balanced elbow pair first. Avoid gratuitous detours just to escape
  // a shared trunk; shared endpoints are expected in a branching workflow.
  const midY = (start.y + end.y) / 2, midX = (start.x + end.x) / 2;
  const simple = [
    [start, {x:start.x,y:midY}, {x:end.x,y:midY}, end],
    [start, {x:midX,y:start.y}, {x:midX,y:end.y}, end],
  ].map(simplify).filter(clear);
  // Prefer the vertical-horizontal-vertical candidate. Its end segments
  // merge with centered card stems; avoiding shared trunks is not a reason
  // to add two more elbows or leave an otherwise empty gap.
  if (simple.length) return simple[0];
  const xs = unique([start.x, end.x, bounds.left, bounds.right, ...preferredX, ...obstacles.flatMap(r => [r.x, r.x + r.width])].filter(x => x >= bounds.left && x <= bounds.right));
  const ys = unique([start.y, end.y, bounds.top, bounds.bottom, ...obstacles.flatMap(r => [r.y, r.y + r.height])].filter(y => y >= bounds.top && y <= bounds.bottom));
  const nx = xs.length, ny = ys.length;
  const xm = xs.slice(1).map((x, i) => (xs[i] + x) / 2), ym = ys.slice(1).map((y, i) => (ys[i] + y) / 2);
  const blocked = new Uint8Array(nx * ny), horizontal = new Uint8Array((nx - 1) * ny), vertical = new Uint8Array(nx * (ny - 1));
  const range = (values: number[], lo: number, hi: number) => values.map((v, i) => v > lo + .001 && v < hi - .001 ? i : -1).filter(i => i >= 0);
  for (const r of obstacles) {
    const x = range(xs, r.x, r.x + r.width), y = range(ys, r.y, r.y + r.height);
    const hx = range(xm, r.x, r.x + r.width), vy = range(ym, r.y, r.y + r.height);
    for (const j of y) { for (const i of x) blocked[j * nx + i] = 1; for (const i of hx) horizontal[j * (nx - 1) + i] = 1; }
    for (const j of vy) for (const i of x) vertical[j * nx + i] = 1;
  }
  const startBase = ys.indexOf(round(start.y)) * nx + xs.indexOf(round(start.x));
  const endBase = ys.indexOf(round(end.y)) * nx + xs.indexOf(round(end.x));
  if (xs.indexOf(round(start.x)) < 0 || xs.indexOf(round(end.x)) < 0 || ys.indexOf(round(start.y)) < 0 || ys.indexOf(round(end.y)) < 0) {
    if (xBounds) return orthogonalRoute(start, end, rectangles, preferredX, used);
    throw new Error('连线路径端点超出搜索范围');
  }
  const scores = new Float64Array(nx * ny * 3).fill(Infinity), previous = new Int32Array(nx * ny * 3).fill(-1);
  const queue = new Queue(); scores[startBase * 3] = 0; queue.push({ id: startBase * 3, score: distance(start, end) });
  let found = -1;
  while (queue.length) {
    const state = queue.pop(), base = Math.floor(state.id / 3), direction = state.id % 3;
    const i = base % nx, j = Math.floor(base / nx), p = { x: xs[i], y: ys[j] };
    if (state.score > scores[state.id] + distance(p, end) + .001) continue;
    if (base === endBase) { found = state.id; break; }
    const neighbors: Array<[number, number, number, boolean]> = [
      [i - 1, j, 1, i > 0 && !horizontal[j * (nx - 1) + i - 1]], [i + 1, j, 1, i + 1 < nx && !horizontal[j * (nx - 1) + i]],
      [i, j - 1, 2, j > 0 && !vertical[(j - 1) * nx + i]], [i, j + 1, 2, j + 1 < ny && !vertical[j * nx + i]],
    ];
    for (const [ni, nj, nd, clear] of neighbors) {
      if (!clear || ni < 0 || nj < 0 || ni >= nx || nj >= ny || blocked[nj * nx + ni]) continue;
      const q = { x: xs[ni], y: ys[nj] }, length = distance(p, q), id = (nj * nx + ni) * 3 + nd;
      const laneBias = preferredX.length && nd === 2 ? Math.min(...preferredX.map(x => Math.abs(q.x - x))) * .00015 * length : 0;
      const score = scores[state.id] + length + (direction && direction !== nd ? 48 : 0) + laneBias + overlapCost(p, q, used) * .15;
      if (score < scores[id]) { scores[id] = score; previous[id] = state.id; queue.push({ id, score: score + distance(q, end) }); }
    }
  }
  if (found < 0) {
    if (!expanded) return orthogonalRoute(start, end, rectangles, preferredX, used, xBounds, true);
    if (xBounds) return orthogonalRoute(start, end, rectangles, preferredX, used);
    throw new Error('未找到避开事件卡片的连线路径');
  }
  const result: RoutePoint[] = [];
  for (let id = found; id >= 0; id = previous[id]) { const base = Math.floor(id / 3); result.push({ x: xs[base % nx], y: ys[Math.floor(base / nx)] }); }
  return simplify(result.reverse());
}

/** A branch or merge can share a bus only if every member fits the same
 * clear inter-row gap. This never joins unrelated endpoint pairs. */
function sharedRelationChannels(rectangles: Map<string, RouteRect>, relations: DisplayEventRelation[],
  primary: (r: DisplayEventRelation) => boolean, eventToTurn: Map<string, string>) {
  const groups = new Map<string, DisplayEventRelation[]>();
  const allRects = [...rectangles.values()].map(r => inflate(r, 8));
  for (const relation of relations) {
    const from = rectangles.get(relation.from)!, to = rectangles.get(relation.to)!;
    if (eventToTurn.get(relation.from) !== eventToTurn.get(relation.to) || from.y + from.height + 28 > to.y) continue;
    const style = `${relation.kind}:${primary(relation)}:${relation.kind === 'logical' ? 'logical' : relation.type}`;
    const layers = `${round(from.y + from.height / 2)}:${round(to.y + to.height / 2)}`;
    for (const endpoint of [`from:${relation.from}`, `to:${relation.to}`]) {
      const id = `${style}:${layers}:${endpoint}`;
      groups.set(id, [...(groups.get(id) || []), relation]);
    }
  }
  const channels = new Map<string, number>();
  for (const [, group] of [...groups].sort((a,b) => b[1].length-a[1].length || a[0].localeCompare(b[0]))) {
    const members = group.filter(r => !channels.has(r.relation_id));
    if (members.length < 2) continue;
    const lo = Math.max(...members.map(r => {const box = rectangles.get(r.from)!; return box.y + box.height + 14;}));
    const hi = Math.min(...members.map(r => rectangles.get(r.to)!.y - 14));
    if (lo > hi) continue;
    const candidates = unique([(lo+hi)/2, lo, hi, ...allRects.flatMap(r => [r.y, r.y+r.height])])
      .filter(y => y >= lo && y <= hi).sort((a,b) => Math.abs(a-(lo+hi)/2)-Math.abs(b-(lo+hi)/2) || a-b);
    const y = candidates.find(y => members.every(r => {
      const from = rectangles.get(r.from)!, to = rectangles.get(r.to)!;
      const start = {x:from.x+from.width/2, y:from.y+from.height+14};
      const end = {x:to.x+to.width/2, y:to.y-14};
      const points = [start,{x:start.x,y},{x:end.x,y},end];
      return points.slice(1).every((p,i) => !allRects.some(box => segmentHitsRect(points[i],p,box)));
    }));
    if (y !== undefined) members.forEach(r => channels.set(r.relation_id,y));
  }
  return channels;
}

/** Align the 6/4 dash pattern on a shared horizontal segment, including merges
 * whose source stems have different lengths or run in opposite directions. */
export function sharedChannelDashOffset(points: RoutePoint[], y?: number) {
  if (y === undefined) return 0;
  let length = 0;
  for (let i=1; i<points.length; i++) {
    const a=points[i-1], b=points[i];
    if (a.y === y && b.y === y && a.x !== b.x) return (b.x > a.x ? a.x : -a.x+6) - length;
    length += distance(a,b);
  }
  return 0;
}

/** Align nearby interior horizontal segments of logical branches/merges.
 * Relation identity is retained; only shared-endpoint paths may share a bus.
 * Side-attached terminal segments stay anchored to their actual card ports. */
function alignLogicalBuses(routes: Map<string, EventEdgeRoute>, relations: DisplayEventRelation[], rectangles: RouteRect[]) {
  const groups = new Map<string, string[]>();
  for (const relation of relations) {
    const route=routes.get(relation.relation_id)!;
    if (relation.kind !== 'logical' || route.sourceHandle !== 'main-out' || route.targetHandle !== 'main-in') continue;
    for (const endpoint of [`from:${relation.from}`,`to:${relation.to}`]) {
      const key=`${route.primary}:${endpoint}`;
      groups.set(key,[...(groups.get(key)||[]),relation.relation_id]);
    }
  }
  const clear=(points:RoutePoint[])=>points.slice(1).every((p,i)=>!rectangles.some(r=>segmentHitsRect(points[i],p,i>0&&i<points.length-2?inflate(r,8):r))) &&
    points[1].y>=points[0].y+14 && points[points.length-2].y<=points[points.length-1].y-14;
  for (const [,ids] of [...groups].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]))) {
    const segments=ids.flatMap(id=>{
      const points=routes.get(id)!.points;
      return points.slice(1).flatMap((p,i)=> i>0 && i+1<points.length-1 && p.y===points[i].y && Math.abs(p.x-points[i].x)>=24
        ? [{id,index:i,y:p.y,lo:Math.min(p.x,points[i].x),hi:Math.max(p.x,points[i].x)}] : []);
    }).sort((a,b)=>a.y-b.y||a.id.localeCompare(b.id));
    const assigned=new Set<string>();
    for (const segment of segments) {
      if(assigned.has(segment.id))continue;
      const peers=segments.filter(s=>!assigned.has(s.id)&&Math.abs(s.y-segment.y)<=36&&Math.min(s.hi,segment.hi)-Math.max(s.lo,segment.lo)>=20);
      if(new Set(peers.map(p=>p.id)).size<2)continue;
      const uniquePeers=[...new Map(peers.map(p=>[p.id,p])).values()];
      const candidates=unique(uniquePeers.map(s=>s.y)).sort((a,b)=>Math.abs(a-segment.y)-Math.abs(b-segment.y)||a-b);
      for(const y of candidates){
        const updates=uniquePeers.map(s=>{
          const points=routes.get(s.id)!.points.map(p=>({...p}));
          points[s.index].y=y;points[s.index+1].y=y;
          return {id:s.id,points:simplify(points)};
        });
        if(!updates.every(u=>clear(u.points)))continue;
        updates.forEach(u=>{const route=routes.get(u.id)!;route.points=u.points;route.sharedChannelY=y;assigned.add(u.id);});
        break;
      }
    }
  }
}

const relationsShareEndpoint = (a: DisplayEventRelation, b: DisplayEventRelation) =>
    a.from === b.from || a.from === b.to || a.to === b.from || a.to === b.to;
const segmentsIntersect = (a: RoutePoint, b: RoutePoint, c: RoutePoint, d: RoutePoint) => {
    if (a.y === b.y && c.y === d.y) return a.y === c.y && Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x)) > Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x)) + .001;
    if (a.x === b.x && c.x === d.x) return a.x === c.x && Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y)) > Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y)) + .001;
    const [h1,h2,v1,v2] = a.y === b.y ? [a,b,c,d] : [c,d,a,b];
    return v1.x >= Math.min(h1.x,h2.x)-.001 && v1.x <= Math.max(h1.x,h2.x)+.001 &&
      h1.y >= Math.min(v1.y,v2.y)-.001 && h1.y <= Math.max(v1.y,v2.y)+.001;
  };

/** Align opposing solid/dashed arms at a shared node without overlaying
 * their different styles. Ports, bend count, and dashed paths remain intact. */
function alignLogicalToDashed(routes: Map<string, EventEdgeRoute>, relations: DisplayEventRelation[],
  rectangles: Map<string, RouteRect>, eventToTurn: Map<string, string>) {
  const anchors = relations.filter(r => !routes.get(r.relation_id)!.primary);
  const allRects = [...rectangles.values()];
  const horizontalIndex = (points: RoutePoint[], incoming: boolean) => {
    const indices = points.slice(1).flatMap((p,i) => i > 0 && i+1 < points.length-1 &&
      points[i].y === p.y && Math.abs(points[i].x-p.x) >= 20 ? [i] : []);
    return incoming ? indices[indices.length-1] : indices[0];
  };
  const conflicts = (points: RoutePoint[], path: RoutePoint[]) => points.slice(1).reduce((count,b,i) =>
    count+path.slice(1).filter((d,j) => segmentsIntersect(points[i],b,path[j],d)).length,0);
  for (const relation of [...relations].sort((a,b) => a.relation_id.localeCompare(b.relation_id))) {
    const route = routes.get(relation.relation_id)!;
    if (relation.kind !== 'logical' || !route.primary || eventToTurn.get(relation.from) !== eventToTurn.get(relation.to)) continue;
    for (const incoming of [false,true]) {
      if (incoming ? route.targetHandle !== 'main-in' : route.sourceHandle !== 'main-out') continue;
      const index = horizontalIndex(route.points,incoming);
      if (index === undefined) continue;
      const a = route.points[index], b = route.points[index+1];
      const candidates = anchors.flatMap(anchor => {
        if (incoming ? anchor.to !== relation.to : anchor.from !== relation.from) return [];
        if (eventToTurn.get(anchor.from) !== eventToTurn.get(anchor.to)) return [];
        const path = routes.get(anchor.relation_id)!;
        if (incoming ? path.targetHandle !== 'main-in' : path.sourceHandle !== 'main-out') return [];
        const ai = horizontalIndex(path.points,incoming);
        if (ai === undefined) return [];
        const c = path.points[ai], d = path.points[ai+1];
        // Opposing arms may meet at the node's centerline; do not paint a
        // logical solid line over a dashed arm that carries another meaning.
        const overlap = Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x))-Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x));
        return Math.abs(a.y-c.y) <= 64 && overlap <= .001 ? [{y:c.y,id:anchor.relation_id}] : [];
      }).sort((x,y) => Math.abs(x.y-a.y)-Math.abs(y.y-a.y) || x.id.localeCompare(y.id));
      for (const candidate of candidates) {
        if (candidate.y === a.y) break;
        const before = route.points[index-1], after = route.points[index+2];
        if ((a.y-before.y)*(candidate.y-before.y) <= 0 ||
            (after.y-b.y)*(after.y-candidate.y) <= 0) continue;
        const points = route.points.map(p => ({...p}));
        points[index].y = candidate.y; points[index+1].y = candidate.y;
        const from = rectangles.get(relation.from)!, to = rectangles.get(relation.to)!;
        const clear = points.slice(1).every((p,i) => !allRects.some(r => segmentHitsRect(points[i],p,
          (i === 0 && r === from || i === points.length-2 && r === to) ? r : inflate(r,8))));
        if (!clear || route.sourceHandle === 'main-out' && points[1].y < points[0].y+14 ||
            route.targetHandle === 'main-in' && points[points.length-2].y > points[points.length-1].y-14) continue;
        if (relations.some(other => other.relation_id !== relation.relation_id && !relationsShareEndpoint(relation,other) &&
          conflicts(points,routes.get(other.relation_id)!.points) > conflicts(route.points,routes.get(other.relation_id)!.points))) continue;
        route.points = points;
        route.sharedChannelY = candidate.y;
        break;
      }
    }
  }
}

export function routeEventRelations(layout: ReturnType<typeof layoutEventTurns>, events: ObserverEvent[], relations: DisplayEventRelation[], workflow: EventWorkflow | null) {
  const levels = new Map(workflow?.event_importance.map(e => [e.event_id, e.level]) || []);
  const turns = new Map(layout.turns.map(turn => [turn.id, turn]));
  const rectangles = new Map(events.map(event => {
    const turn = turns.get(layout.eventToTurn.get(event.event_id)!)!, p = layout.positions.get(event.event_id)!, size = layout.sizes.get(event.event_id)!;
    return [event.event_id, { x: turn.x + p.x, y: turn.y + p.y, width: size.width, height: size.height }];
  }));
  const allRects = [...rectangles.values()], used: Segment[] = [], labels: RouteRect[] = [];
  const result = new Map<string, EventEdgeRoute>();
  const primary = (r: DisplayEventRelation) => r.confidence !== 'low' && (
    r.kind === 'logical' && (layout.primaryEventIds.has(r.from) || layout.primaryEventIds.has(r.to) || isRoutineEvent(levels.get(r.from)) && isRoutineEvent(levels.get(r.to))) ||
    r.kind === 'rule' && isKeyEvent(levels.get(r.from)) && isKeyEvent(levels.get(r.to))
  );
  const channels = sharedRelationChannels(rectangles, relations, primary, layout.eventToTurn);
  const corridorByTurn=new Map(layout.turns.map(turn=>{
    const main=turn.events.filter(e=>layout.primaryEventIds.has(e.event_id)).map(e=>rectangles.get(e.event_id)!);
    const side=turn.events.filter(e=>!layout.primaryEventIds.has(e.event_id)).map(e=>rectangles.get(e.event_id)!);
    const right=main.length?Math.max(...main.map(r=>r.x+r.width)):turn.x;
    const left=side.length?Math.min(...side.map(r=>r.x)):right;
    return [turn.id,left-right>=28?(left+right)/2:undefined];
  }));
  const port = (r: RouteRect, top: boolean) => ({ x: r.x + r.width / 2, y: r.y + (top ? 0 : r.height) });
  const ordered = [...relations].sort((a, b) => Number(primary(b)) - Number(primary(a)) || distance(port(rectangles.get(a.from)!, false), port(rectangles.get(a.to)!, true)) - distance(port(rectangles.get(b.from)!, false), port(rectangles.get(b.to)!, true)) || a.relation_id.localeCompare(b.relation_id));
  const escape = (origin: RoutePoint, own: RouteRect, dx: number, dy: number) => {
    const candidates = [14, 8].map(length => ({x:origin.x+dx*length,y:origin.y+dy*length}));
    return candidates.find(p => !allRects.some(r => r !== own && segmentHitsRect(origin,p,inflate(r,8)))) ?? candidates[0];
  };
  // Build and merge the normal bottom-to-top routes first. Equal bend counts
  // must keep these ports even when a side route would be shorter.
  for (const relation of ordered) {
    const from = rectangles.get(relation.from)!, to = rectangles.get(relation.to)!;
    const sourceTurn = turns.get(layout.eventToTurn.get(relation.from)!)!, targetTurn = turns.get(layout.eventToTurn.get(relation.to)!)!;
    const axis = sourceTurn.x + sourceTurn.centerX;
    const start = port(from, false), end = port(to, true);
    const exit = escape(start, from, 0, 1), entry = escape(end, to, 0, -1);
    const sharedChannelY = channels.get(relation.relation_id);
    let middle: RoutePoint[];
    if (sharedChannelY !== undefined) {
      middle = simplify([exit, {x:exit.x,y:sharedChannelY}, {x:entry.x,y:sharedChannelY}, entry]);
    } else if (sourceTurn.id !== targetTurn.id) {
      const forward = targetTurn.x > sourceTurn.x;
      const corridor = forward ? (sourceTurn.x + sourceTurn.width + targetTurn.x) / 2
        : (targetTurn.x + targetTurn.width + sourceTurn.x) / 2;
      middle = orthogonalRoute(exit, entry, allRects, [corridor], used);
    } else {
      const preferred = [axis, axis - sourceTurn.primaryExtent - 24, axis + sourceTurn.primaryExtent + 24];
      middle = orthogonalRoute(exit, entry, allRects, preferred, used,
        [sourceTurn.x + 12, sourceTurn.x + sourceTurn.width - 12]);
    }
    const points = simplify([start, ...middle, end]);
    for (let i = 1; i < points.length; i++) used.push([points[i - 1], points[i]]);
    result.set(relation.relation_id, { primary: primary(relation), points, sharedChannelY,
      sourceHandle: 'main-out', targetHandle: 'main-in' });
  }
  alignLogicalBuses(result, relations, allRects);

  // Side ports are an optional simplification, never a blanket routing mode.
  // Test the whole graph, including later edges, before accepting a shortcut.
  const noLineConflicts = (points: RoutePoint[], relation: DisplayEventRelation) => !ordered.some(other => {
    if (other.relation_id === relation.relation_id || relationsShareEndpoint(relation, other)) return false;
    const path = result.get(other.relation_id)!.points;
    return points.slice(1).some((b,i) => path.slice(1).some((d,j) => segmentsIntersect(points[i],b,path[j],d)));
  });
  type Port = { point: RoutePoint; dx: number; dy: number; handle: string };
  const length = (points: RoutePoint[]) => points.slice(1).reduce((n,p,i) => n+distance(points[i],p),0);
  for (const relation of ordered) {
    const original = result.get(relation.relation_id)!;
    const from = rectangles.get(relation.from)!, to = rectangles.get(relation.to)!;
    const turnId = layout.eventToTurn.get(relation.from)!;
    if (relation.kind !== 'logical' || turnId !== layout.eventToTurn.get(relation.to) || original.points.length <= 3) continue;
    const fromKey = isKeyEvent(levels.get(relation.from)), toKey = isKeyEvent(levels.get(relation.to));
    if (!fromKey && !toKey) continue;
    const sourcePorts: Port[] = [{point:port(from,false),dx:0,dy:1,handle:'main-out'}];
    const targetPorts: Port[] = [{point:port(to,true),dx:0,dy:-1,handle:'main-in'}];
    if (fromKey) sourcePorts.push({point:{x:from.x+from.width,y:from.y+from.height/2},dx:1,dy:0,handle:'lateral-out-right'});
    else if (from.x >= to.x+to.width+28) sourcePorts.push({point:{x:from.x,y:from.y+from.height/2},dx:-1,dy:0,handle:'lateral-out-left'});
    if (toKey) targetPorts.push({point:{x:to.x+to.width,y:to.y+to.height/2},dx:1,dy:0,handle:'lateral-in-right'});
    else if (to.x >= from.x+from.width+28) targetPorts.push({point:{x:to.x,y:to.y+to.height/2},dx:-1,dy:0,handle:'lateral-in-left'});
    const candidates: EventEdgeRoute[] = [];
    for (const source of sourcePorts) for (const target of targetPorts) {
      // Only introduce a side port to use a core card's right edge. Changing
      // just the secondary card to its left port is not a core-side shortcut.
      if (!(fromKey && source.handle === 'lateral-out-right') &&
          !(toKey && target.handle === 'lateral-in-right')) continue;
      const exit = escape(source.point,from,source.dx,source.dy), entry = escape(target.point,to,target.dx,target.dy);
      const corridor = corridorByTurn.get(turnId) ?? Math.max(from.x+from.width,to.x+to.width)+24;
      const middleCandidates = [
        [exit,{x:exit.x,y:entry.y},entry],
        [exit,{x:entry.x,y:exit.y},entry],
        [exit,{x:corridor,y:exit.y},{x:corridor,y:entry.y},entry],
      ];
      for (const middle of middleCandidates) {
        const points = simplify([source.point,...middle,target.point]);
        if (points.length >= original.points.length || points.length < 2) continue;
        const first = points[1], last = points[points.length-2];
        if ((first.x-source.point.x)*source.dx+(first.y-source.point.y)*source.dy <= 0 ||
            (last.x-target.point.x)*target.dx+(last.y-target.point.y)*target.dy <= 0) continue;
        // All segments are checked, including terminal stubs. The owning card
        // is exempt only from its own inflated clearance at the port.
        const clear = points.slice(1).every((b,i) => !allRects.some(r => segmentHitsRect(points[i],b,
          i === 0 && r === from || i === points.length-2 && r === to ? r : inflate(r,8))));
        if (!clear || !noLineConflicts(points,relation)) continue;
        candidates.push({primary:original.primary,points,sourceHandle:source.handle,targetHandle:target.handle});
      }
    }
    candidates.sort((a,b) => a.points.length-b.points.length || length(a.points)-length(b.points) ||
      Number(b.sourceHandle === 'main-out')-Number(a.sourceHandle === 'main-out'));
    if (candidates.length) result.set(relation.relation_id,candidates[0]);
  }
  alignLogicalToDashed(result, relations, rectangles, layout.eventToTurn);
  for(const route of result.values()){
    const points=route.points,key=route.primary;
    let labelPosition: RoutePoint | undefined;
    if (key) {
      const candidates = points.slice(1).flatMap((b, i) => [.5, .25, .75].map(t => ({ x: points[i].x + (b.x - points[i].x) * t, y: points[i].y + (b.y - points[i].y) * t, length: distance(points[i], b) })));
      candidates.sort((a, b) => b.length - a.length);
      for (const p of candidates) {
        const box = { x: p.x - 42, y: p.y - 12, width: 84, height: 24 };
        if (!allRects.some(r => overlaps(box, inflate(r, 6))) && !labels.some(r => overlaps(box, inflate(r, 4)))) { labelPosition = { x: p.x, y: p.y }; labels.push(box); break; }
      }
    }
    route.labelPosition=labelPosition;
  }
  return result;
}
