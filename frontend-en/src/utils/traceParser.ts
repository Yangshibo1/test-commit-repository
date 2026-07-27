import { ProvNode, ProvEdge, SessionFiles, TraceData, LlmArtifact, StepDetail, ArtifactMatchResult } from '../types';

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
  if (!name) return '';

  // Step 1: 提取文件名（去除路径）
  const fileName = name.split(/[\\/]/).pop() || name;

  // Step 2: 去除已知的扩展名
  let result = fileName
    .replace(/\.analysis\.json$/i, '')
    .replace(/\.json$/i, '')
    .replace(/\.py$/i, '')
    .replace(/\.txt$/i, '')
    .toLowerCase();

  console.log(`[artifactBaseName] Input: "${name}" -> FileName: "${fileName}" -> Result: "${result}"`);
  return result;
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
  const result = findLlmArtifactWithDiagnostics(trace, options);
  return result.artifact;
}

export function findLlmArtifactWithDiagnostics(trace: TraceData, options: { step?: StepDetail; node?: ProvNode }): ArtifactMatchResult {
  const artifacts = trace.llmArtifacts || {};
  const artifactKeys = Object.keys(artifacts);

  // 简化匹配逻辑：只使用节点的 location 或 name 字段进行精确匹配
  // 不使用 step_id 或其他字段，避免误匹配
  let matchKey: string | null = null;

  if (options.node) {
    // 优先使用 location（Entity 节点的文件路径）
    if (options.node.location) {
      matchKey = artifactBaseName(options.node.location);
      console.log(`[ArtifactMatch] Trying location: "${options.node.location}" -> "${matchKey}"`);
    }
    // 如果没有 location，使用 name（Agent 节点的名称）
    if (!matchKey && options.node.name) {
      matchKey = artifactBaseName(options.node.name);
      console.log(`[ArtifactMatch] Trying name: "${options.node.name}" -> "${matchKey}"`);
    }
  }

  if (matchKey && artifacts[matchKey]) {
    console.log(`[ArtifactMatch] Exact match: "${matchKey}" -> artifact`);
    return {
      artifact: artifacts[matchKey],
      matchedKey: matchKey,
      candidates: [matchKey],
      matchType: 'exact',
      similarityScore: 1.0
    };
  }

  console.log(`[ArtifactMatch] No match found. Tried: "${matchKey}"`);
  console.log(`[ArtifactMatch] Available artifacts:`, artifactKeys);

  return {
    artifact: null,
    matchedKey: null,
    candidates: matchKey ? [matchKey] : [],
    matchType: 'none'
  };
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
