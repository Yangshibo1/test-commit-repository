import { ProvNode, ProvEdge, SessionFiles, TraceData, LlmArtifact, StepDetail } from '../types';

const REQUIRED_FILES = ['step_details.json', 'prov_nodes.json', 'prov_edges.json', 'prov_dag.json'];

export function parseSessionFiles(files: SessionFiles): TraceData | null {
  const stepDetails = files['step_details.json'];
  const provNodes = files['prov_nodes.json']?.nodes || {};
  const provEdges = files['prov_edges.json']?.edges || [];
  const dag = files['prov_dag.json'] || {};
  const meta = files['meta.json'] || {};

  const nodes = Object.values(provNodes);
  const entities = nodes.filter((n) => n.type === 'entity');
  const activities = nodes.filter((n) => n.type === 'activity');
  const agents = nodes.filter((n) => n.type === 'agent');
  const llmArtifacts = collectLlmArtifacts(files);

  const steps: StepDetail[] = (stepDetails?.steps || []).map((step, index) => {
    const operation = String(step.parameters?.operation || inferOperation(step));
    return {
      step_id: step.step_id || `step_${String(index + 1).padStart(3, '0')}`,
      step_name: step.step_name || step.name || 'unnamed_step',
      name: step.step_name || step.name || 'unnamed_step',
      description: step.description || '',
      timestamp: step.timestamp || '',
      input_files: step.input_files || [],
      output_files: step.output_files || [],
      code_files: step.code_files || [],
      code_generated: step.code_generated || [],
      commands_run: step.commands_run || [],
      parameters: step.parameters || {},
      index: index + 1,
      operation,
    };
  });

  return {
    sessionId: stepDetails?.session_id || (meta as any).session_id || (dag as any).session_id || 'unidentified_session',
    createdAt: (meta as any).created_at || (stepDetails as any).created_at || (dag as any).created_at || 'unknown',
    steps,
    prov: { nodes: provNodes, edges: provEdges },
    llmArtifacts,
    counts: {
      entities: entities.length,
      activities: activities.length,
      agents: agents.length,
      edges: provEdges.length,
      artifacts: Object.keys(llmArtifacts).length,
    },
    consistency: checkConsistency(files, steps, meta as Record<string, unknown>),
  };
}

function inferOperation(step: any): string {
  const joined = `${step.step_name || step.name || ''} ${step.description || ''}`.toLowerCase();
  for (const key of ['load', 'filter', 'trace', 'aggregate', 'visualize', 'validate', 'transform', 'analyze']) {
    if (joined.includes(key)) return key;
  }
  return 'analysis_node';
}

function collectLlmArtifacts(files: SessionFiles): Record<string, LlmArtifact> {
  const artifacts: Record<string, LlmArtifact> = {};
  for (const [name, data] of Object.entries(files)) {
    if (!/\.analysis\.json$/i.test(name) || !data || typeof data !== 'object') continue;
    const key = artifactBaseName(name);
    if (key) {
      artifacts[key] = data as LlmArtifact;
    }
  }
  return artifacts;
}

function artifactBaseName(name: string): string {
  return (name || '')
    .replace(/\.analysis\.json$/i, '')
    .replace(/\.(py|json|txt)$/i, '')
    .toLowerCase();
}

function checkConsistency(files: SessionFiles, steps: StepDetail[], meta: Record<string, unknown>): { ok: boolean; warnings: string[] } {
  const missing = REQUIRED_FILES.filter((name) => !files[name]);
  const warnings: string[] = [];
  if (missing.length) warnings.push(`missing: ${missing.join(', ')}`);
  if (meta.total_steps && Number(meta.total_steps) !== steps.length) {
    warnings.push(`meta total_steps (${meta.total_steps}) differs from step_details (${steps.length})`);
  }
  return { ok: warnings.length === 0, warnings };
}

export function findLlmArtifact(trace: TraceData, options: { step?: StepDetail; node?: ProvNode }): LlmArtifact | null {
  const artifacts = trace.llmArtifacts || {};
  const candidates: string[] = [];

  const pushCandidate = (value: string | undefined) => {
    if (!value) return;
    const key = artifactBaseName(value);
    if (key) candidates.push(key);
  };

  pushCandidate(options.node?.location);
  pushCandidate(options.node?.name);
  pushCandidate(options.node?.description);
  for (const file of options.step?.code_files || []) pushCandidate(file);
  for (const file of options.step?.output_files || []) pushCandidate(file);
  for (const file of options.step?.input_files || []) pushCandidate(file);
  pushCandidate(options.step?.name);
  pushCandidate(options.step?.step_id);

  for (const key of candidates) {
    if (artifacts[key]) return artifacts[key];
  }

  for (const key of candidates) {
    const foundKey = Object.keys(artifacts).find((artifactKey) =>
      key && (artifactKey.includes(key) || key.includes(artifactKey))
    );
    if (foundKey) return artifacts[foundKey];
  }

  return null;
}

export function baseName(path: string): string {
  if (!path) return 'unknown';
  return String(path).split(/[\\/]/).pop() || path || 'unknown';
}

export function buildProvDAGFlow(trace: TraceData): { nodes: ProvNode[]; edges: ProvEdge[] } {
  const nodes = trace.prov.nodes || {};
  const edges = trace.prov.edges || [];
  const activities = Object.values(nodes).filter((n) => n.type === 'activity');

  const locationToNode = new Map<string, ProvNode>();
  const entityIdToMergedId = new Map<string, string>();
  const agentKeyToNode = new Map<string, ProvNode>();
  const agentIdToMergedId = new Map<string, string>();
  const agentNodes: Record<string, ProvNode> = {};
  const activityNodes: Record<string, ProvNode> = {};
  const mergedConnections: ProvEdge[] = [];
  const seenConnections = new Set<string>();

  function mergeEntityByLocation(entity: ProvNode): ProvNode {
    const location = entity.location || entity.id;
    const locationKey = normalizeArtifactLocation(location || '');
    if (!locationToNode.has(locationKey)) {
      locationToNode.set(locationKey, {
        ...entity,
        id: `artifact_${locationToNode.size}`,
        location,
        original_ids: [],
        merged: true,
      });
    }
    const merged = locationToNode.get(locationKey)!;
    merged.original_ids = merged.original_ids || [];
    merged.original_ids!.push(entity.id);
    entityIdToMergedId.set(entity.id, merged.id);
    return merged;
  }

  Object.values(nodes).filter((n) => n.type === 'entity').forEach(mergeEntityByLocation);

  Object.values(nodes).filter((n) => n.type === 'agent').forEach((agent) => {
    const mergedAgent = mergeAgentByName(agent, agentKeyToNode);
    agentNodes[mergedAgent.id as string] = mergedAgent;
    agentIdToMergedId.set(agent.id, mergedAgent.id);
  });

  activities.forEach((activity) => {
    activityNodes[activity.id as string] = activity;
  });

  for (const activity of activities) {
    const used = edges
      .filter((e) => e.from === activity.id && e.relation === 'used')
      .map((e) => entityIdToMergedId.get(e.to))
      .filter(Boolean);
    const generated = edges
      .filter((e) => e.to === activity.id && e.relation === 'wasGeneratedBy')
      .map((e) => entityIdToMergedId.get(e.from))
      .filter(Boolean);
    const associated = edges
      .filter((e) => e.from === activity.id && e.relation === 'wasAssociatedWith')
      .map((e) => agentIdToMergedId.get(e.to))
      .filter((id): id is string => id !== undefined && agentNodes[id] !== undefined);

    const agentIds = associated.length ? associated : [`activity_proxy_${activity.id}`];

    if (!associated.length) {
      agentNodes[agentIds[0] as string] = {
        id: agentIds[0],
        type: 'agent',
        agent_type: 'activity_proxy',
        name: activity.description || activity.activity_type || activity.id,
        attributes: { proxied_activity: activity.id },
      };
    }

    for (const input of used) {
      for (const agentId of agentIds) {
        const key = dedupeRelationKey(input || '', agentId || '', activity.activity_type || 'process');
        if (!seenConnections.has(key)) {
          seenConnections.add(key);
          mergedConnections.push({ from: input || '', to: agentId || '', relation: activity.activity_type || 'process' });
        }
      }
    }

    for (const agentId of agentIds) {
      for (const output of generated) {
        const key = dedupeRelationKey(agentId || '', output || '', 'output');
        if (!seenConnections.has(key)) {
          seenConnections.add(key);
          mergedConnections.push({ from: agentId || '', to: output || '', relation: 'output' });
        }
      }
    }
  }

  for (const edge of edges.filter((e) => e.relation === 'wasDerivedFrom')) {
    const from = entityIdToMergedId.get(edge.to);
    const to = entityIdToMergedId.get(edge.from);
    const key = dedupeRelationKey(from || '', to || '', 'wasDerivedFrom');
    if (from && to && from !== to && !seenConnections.has(key)) {
      seenConnections.add(key);
      mergedConnections.push({ from, to, relation: 'wasDerivedFrom' });
    }
  }

  const artifactNodes = Array.from(locationToNode.values());
  const ordered = [...artifactNodes, ...Object.values(agentNodes)];

  return { nodes: ordered, edges: mergedConnections };
}

function mergeAgentByName(agent: ProvNode, agentKeyToNode: Map<string, ProvNode>): ProvNode {
  const key = (agent.name || agent.id || 'agent').trim().toLowerCase();
  if (!agentKeyToNode.has(key)) {
    agentKeyToNode.set(key, {
      ...agent,
      id: `agent_merged_${agentKeyToNode.size}`,
      original_ids: [],
    });
  }
  const merged = agentKeyToNode.get(key)!;
  merged.original_ids = merged.original_ids || [];
  merged.original_ids!.push(agent.id);
  return merged;
}

function dedupeRelationKey(from: string, to: string, relation: string): string {
  return `${from}|${to}|${relation}`;
}

function normalizeArtifactLocation(location: string): string {
  if (!location) return '';
  return String(location)
    .replace(/\\/g, '/')
    .replace(/\/\.\//g, '/')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}
