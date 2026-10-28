import dagre from 'dagre';
import type { ObserverEvent, ObserverTrace } from '../types/observer';
import type { EventWorkflow } from '../types/eventWorkflow';
import { eventNodeSize, isKeyEvent, isRoutineEvent } from './eventWorkflow.ts';
import type { DisplayEventRelation } from './eventWorkflow';

export interface EventTurnSection {
  id: string; turn_id: string | null; ordinal: number; title: string;
  prompt_event_id?: string; events: ObserverEvent[];
}

/** Scope is authoritative; the recorded turn membership is the compatibility fallback. */
export function groupEventsByTurn(trace: ObserverTrace): EventTurnSection[] {
  const membership = new Map<string, string>();
  const metadata = new Map((trace.turns || []).map(turn => [turn.turn_id, turn]));
  for (const turn of trace.turns || []) for (const id of turn.event_ids) {
    if (!membership.has(id)) membership.set(id, turn.turn_id);
  }
  const groups = new Map<string | null, ObserverEvent[]>();
  const sorted = [...trace.events].sort((a, b) => a.sequence - b.sequence || a.event_id.localeCompare(b.event_id));
  for (const event of sorted) {
    const key = event.scope?.turn_id || event.turn_id || membership.get(event.event_id) || null;
    groups.set(key, [...(groups.get(key) || []), event]);
  }
  const sections = [...groups.entries()].map(([key, events]) => {
    const recorded = key ? metadata.get(key) : undefined;
    const prompt = events.find(e => e.event_id === recorded?.prompt_event_id) || events.find(e => e.event_type === 'user_prompt');
    return {
      id: key === null ? 'turn-unassigned' : `turn-section-${key}`, turn_id: key, ordinal: 0,
      title: recorded?.prompt || (typeof prompt?.payload?.content === 'string' ? prompt.payload.content : prompt?.title) || '执行记录',
      prompt_event_id: prompt?.event_id, events,
      order: prompt?.sequence ?? events[0].sequence,
    };
  }).sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  let ordinal = 0;
  return sections.map(({ order: _order, ...section }) => ({ ...section, ordinal: section.turn_id ? ++ordinal : 0 }));
}

/** Independent top-down DAGs, aligned at the top and ordered left to right. */
export function layoutEventTurns(trace: ObserverTrace, workflow: EventWorkflow | null, relations: DisplayEventRelation[], weighted: boolean, artifactEventIds: ReadonlySet<string> = new Set()) {
  const sections = groupEventsByTurn(trace);
  const importance = new Map(workflow?.event_importance.map(event => [event.event_id, event.level]) || []);
  const sizes = new Map(trace.events.map(event => {
    const size = eventNodeSize(importance.get(event.event_id), weighted);
    return [event.event_id, { ...size, height: size.height + (artifactEventIds.has(event.event_id) ? 30 : 0) }];
  }));
  const local = sections.map(section => {
    const graph = new dagre.graphlib.Graph();
    graph.setGraph({ rankdir: 'TB', ranksep: 86, nodesep: 44, marginx: 24, marginy: 12 });
    graph.setDefaultEdgeLabel(() => ({}));
    const ids = new Set(section.events.map(event => event.event_id));
    section.events.forEach(event => graph.setNode(event.event_id, { ...sizes.get(event.event_id)! }));
    const within = relations.filter(relation => ids.has(relation.from) && ids.has(relation.to));
    within.forEach(relation => graph.setEdge(relation.from, relation.to, { weight: relation.kind === 'logical' ? 2 : 1 }));
    // Put the user's task before otherwise-disconnected roots. These are layout constraints only.
    if (section.prompt_event_id) {
      const incoming = new Set(within.map(relation => relation.to));
      section.events.filter(event => event.event_id !== section.prompt_event_id && !incoming.has(event.event_id))
        .forEach(event => graph.setEdge(section.prompt_event_id!, event.event_id, { weight: 0 }));
    }
    dagre.layout(graph);
    const core = section.events.filter(event => isKeyEvent(importance.get(event.event_id)));
    const fallback = section.events.filter(event => isRoutineEvent(importance.get(event.event_id)) || !importance.has(event.event_id));
    const primary = new Set((core.length ? core : fallback).map(event => event.event_id));
    if (section.prompt_event_id) primary.add(section.prompt_event_id);
    const layers = new Map<number, ObserverEvent[]>();
    section.events.forEach(event => { const y = graph.node(event.event_id).y; layers.set(y, [...(layers.get(y) || []), event]); });
    const primaryWidth = Math.max(196, ...section.events.filter(event => primary.has(event.event_id)).map(event => sizes.get(event.event_id)!.width));
    const sideWidth = Math.max(196, ...section.events.filter(event => !primary.has(event.event_id)).map(event => sizes.get(event.event_id)!.width));
    const pitch = primaryWidth + 44;
    const primaryExtent = Math.max(primaryWidth/2, ...[...layers.values()].map(events => {
      const count=events.filter(event=>primary.has(event.event_id)).length;
      return count ? (count-1)*pitch+primaryWidth/2 : 0;
    }));
    const sideBase=primaryExtent+52+sideWidth/2;
    const centered=new Map<string,number>();
    for (const [,events] of [...layers].sort((a,b)=>a[0]-b[0])) {
      const bySequence=(a:ObserverEvent,b:ObserverEvent)=>a.sequence-b.sequence||a.event_id.localeCompare(b.event_id);
      events.filter(e=>primary.has(e.event_id)).sort(bySequence)
        .forEach((event,index)=>centered.set(event.event_id,index*pitch));
      events.filter(e=>!primary.has(e.event_id)).sort(bySequence)
        .forEach((event,index)=>centered.set(event.event_id,sideBase+index*(sideWidth+44)));
    }
    // The first primary column is the left spine; secondary events only expand right.
    const axis=52+primaryWidth/2;
    const rightExtent=Math.max(primaryWidth/2,...section.events.map(e=>centered.get(e.event_id)!+sizes.get(e.event_id)!.width/2));
    const width=axis+rightExtent+52;
    return { section, graph, centered, primary, width, primaryExtent, axis, height: graph.graph().height || 0 };
  });
  const positions = new Map<string, {x: number; y: number}>();
  const eventToTurn = new Map<string, string>();
  let x = 40;
  const primaryEventIds = new Set<string>();
  const turns = local.map(({ section, graph, centered, primary, width: localWidth, primaryExtent, axis, height }) => {
    const sectionWidth = Math.max(420, localWidth + 32);
    const box = { ...section, x, y: 32, width: sectionWidth, centerX: axis, primaryExtent, height: height + 94 };
    for (const event of section.events) {
      const position = graph.node(event.event_id), size = sizes.get(event.event_id)!;
      positions.set(event.event_id, { x: axis + centered.get(event.event_id)! - size.width / 2, y: position.y - size.height / 2 + 74 });
      eventToTurn.set(event.event_id, section.id);
      if (primary.has(event.event_id)) primaryEventIds.add(event.event_id);
    }
    x += sectionWidth + 120;
    return box;
  });
  return { turns, positions, eventToTurn, primaryEventIds, sizes, width: Math.max(0, x - 120), height: Math.max(0, ...turns.map(turn => turn.y + turn.height)) };
}
