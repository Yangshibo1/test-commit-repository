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

/**
 * 计算两个字符串的相似度
 * 返回 0-1 之间的值，1 表示完全匹配
 */
function calculateSimilarity(a: string, b: string): number {
  // 精确匹配
  if (a === b) return 1.0;

  // 前缀匹配 (node_01 匹配 node_01_load_data)
  const [shorter, longer] = a.length < b.length ? [a, b] : [b, a];
  if (longer.startsWith(shorter) && shorter.length > 3) {
    // 短字符串至少有 3 个字符且是长字符串的前缀
    const lengthRatio = shorter.length / longer.length;
    // 只有当短字符串长度超过长字符串的 40% 时才匹配
    // 避免 "node_12" 匹配 "node_12_analyze_john_all_posts" (7/27 ≈ 26%)
    if (lengthRatio >= 0.4) {
      return 0.85 + lengthRatio * 0.15; // 0.91-1.0
    }
  }

  // 后缀匹配
  if (longer.endsWith(shorter) && shorter.length > 3) {
    const lengthRatio = shorter.length / longer.length;
    // 同样需要长度比例 >= 40%
    if (lengthRatio >= 0.4) {
      return 0.85 + lengthRatio * 0.15;
    }
  }

  // 包含匹配 (更严格的条件)
  if (longer.includes(shorter) && shorter.length > 4) {
    // 只有当短字符串长度合理且不是单个词时才匹配
    const lengthRatio = shorter.length / longer.length;
    if (lengthRatio > 0.2) { // 至少占长字符串的 20%
      return 0.7 + lengthRatio * 0.1; // 0.72-0.8
    }
  }

  // 词重叠匹配 (node_01_xxx 和 node_01_yyy 应该有较高相似度)
  const aWords = a.split(/[_-]/).filter(w => w.length > 1);
  const bWords = b.split(/[_-]/).filter(w => w.length > 1);

  if (aWords.length > 0 && bWords.length > 0) {
    const commonWords = aWords.filter(w => bWords.includes(w));
    const overlapRatio = commonWords.length / Math.max(aWords.length, bWords.length);

    if (overlapRatio > 0) {
      // 需要至少有 30% 的词重叠才匹配
      if (overlapRatio >= 0.3) {
        return 0.5 + overlapRatio * 0.3; // 0.59-0.8
      }
    }
  }

  // 编辑距离匹配 (对于非常相似但有拼写错误的情况)
  const maxLen = Math.max(a.length, b.length);
  if (maxLen > 0) {
    const editDist = levenshteinDistance(a, b);
    const editSimilarity = 1 - editDist / maxLen;
    // 更严格的编辑距离阈值：需要 > 75% 相似度
    if (editSimilarity > 0.75) return editSimilarity * 0.5; // 0.375-0.5
  }

  return 0;
}

/**
 * 计算 Levenshtein 编辑距离
 */
function levenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];

  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }

  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          matrix[i][j - 1] + 1,     // insertion
          matrix[i - 1][j] + 1      // deletion
        );
      }
    }
  }

  return matrix[b.length][a.length];
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
