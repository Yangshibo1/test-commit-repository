import type { ObserverArtifact, ObserverTrace } from '../types/observer';

export const artifactCategories = [
  { type: 'code', label: '代码', color: '#0f766e' },
  { type: 'dataset', label: '数据集', color: '#2563eb' },
  { type: 'report', label: '报告', color: '#b76b38' },
  { type: 'visualization', label: '可视化', color: '#7c3aed' },
] as const;

export interface NumberedArtifact extends ObserverArtifact { label: string; color: string }
export interface EventArtifactLink { artifact: NumberedArtifact; operations: string[] }

export function artifactOperationLabel(operation: string) {
  return ({ read: '读取', created: '写入/生成', modified: '修改', executed: '运行' } as Record<string, string>)[operation] || operation;
}

/** Number the complete session before any view filtering, without changing source facts. */
export function indexEventArtifacts(trace: Pick<ObserverTrace, 'events' | 'artifacts'>) {
  const sequence = new Map(trace.events.map(event => [event.event_id, event.sequence]));
  const first = (artifact: ObserverArtifact) => Math.min(...artifact.operations.map(op => sequence.get(op.event_id) ?? Infinity));
  const counters = new Map<string, number>();
  const artifacts = [...(trace.artifacts || [])].sort((a, b) => first(a) - first(b) || a.path.localeCompare(b.path)).map(artifact => {
    const category = artifactCategories.find(item => item.type === artifact.artifact_type);
    const index = artifact.category_index || (counters.get(artifact.artifact_type) || 0) + 1;
    counters.set(artifact.artifact_type, Math.max(index, counters.get(artifact.artifact_type) || 0));
    return { ...artifact, label: `${category?.label || '文件'}${index}`, color: category?.color || '#78716c' };
  });
  const byEvent = new Map<string, EventArtifactLink[]>();
  for (const artifact of artifacts) {
    const operations = new Map<string, string[]>();
    for (const op of artifact.operations) operations.set(op.event_id, [...new Set([...(operations.get(op.event_id) || []), artifactOperationLabel(op.operation)])]);
    for (const [id, labels] of operations) byEvent.set(id, [...(byEvent.get(id) || []), { artifact, operations: labels }]);
  }
  return { artifacts, byEvent };
}
