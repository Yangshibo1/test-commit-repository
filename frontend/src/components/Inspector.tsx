import { useState, useEffect } from 'react';
import { ProvNode, StepDetail, LlmArtifact, TraceData, ArtifactMatchResult } from '../types';
import { findLlmArtifact, baseName, findLlmArtifactWithDiagnostics } from '../utils/traceParser';
import * as echarts from 'echarts';

interface InspectorProps {
  selectedProvNode?: ProvNode;
  selectedStep?: StepDetail;
  trace?: TraceData;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

export default function Inspector({ selectedProvNode, selectedStep, trace, isExpanded = false, onToggleExpand }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'files' | 'code' | 'echart' | 'report' | 'parameters'>('overview');
  const [chartRef, setChartRef] = useState<HTMLDivElement | null>(null);

  const matchResult: ArtifactMatchResult | null = trace ? findLlmArtifactWithDiagnostics(trace, { step: selectedStep, node: selectedProvNode }) : null;
  const artifact = matchResult?.artifact || null;
  const artifactKind = artifact ? getArtifactKind(artifact) : null;

  const title = selectedProvNode?.description || selectedProvNode?.name || selectedStep?.name || 'Selection';
  const summary = selectedStep?.description || selectedProvNode?.location || '';

  // 根据节点类型判断（用于没有匹配到 artifact 的情况）
  const getNodeType = (): 'dataset' | 'report' | 'code' | 'other' => {
    if (!selectedProvNode) return 'other';

    // Agent 节点是 code
    if (selectedProvNode.type === 'agent') return 'code';

    // Entity 节点需要进一步判断
    if (selectedProvNode.type === 'entity') {
      const location = selectedProvNode.location || '';
      // 报告类文件
      if (location.match(/(final_report|visualization|validation_result|\.txt$)/i)) {
        return 'report';
      }
      // 其他 Entity 都是 dataset
      return 'dataset';
    }

    return 'other';
  };

  // 根据是否有 artifact 和 step 来决定显示哪些 tabs
  const getAvailableTabs = (): Array<'overview' | 'files' | 'code' | 'echart' | 'report' | 'parameters'> => {
    const hasArtifact = !!artifact;

    // 优先使用 artifactKind，如果没有 artifact 则使用节点类型
    const effectiveKind = artifactKind || (hasArtifact ? null : getNodeType());

    if (effectiveKind === 'dataset') {
      return ['overview', 'files', 'echart', 'parameters'];
    }
    if (effectiveKind === 'report') {
      return ['overview', 'files', 'report', 'parameters'];
    }
    if (effectiveKind === 'code') {
      return ['overview', 'files', 'code', 'parameters'];
    }

    // 默认 tabs（没有 artifact 且无法判断节点类型）
    return ['overview', 'files', 'parameters'];
  };

  const tabs = getAvailableTabs();

  useEffect(() => {
    if (activeTab === 'echart' && artifactKind === 'dataset' && chartRef && artifact?.echarts_chart) {
      const chart = echarts.init(chartRef);
      chart.setOption(artifact.echarts_chart as any, true);
      const resizeHandler = () => chart.resize();
      window.addEventListener('resize', resizeHandler);
      return () => {
        window.removeEventListener('resize', resizeHandler);
        chart.dispose();
      };
    }
  }, [activeTab, artifactKind, artifact, chartRef]);

  if (!selectedProvNode && !selectedStep) {
    return (
      <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
        Click a step or node to view inputs, outputs, code, commands, parameters, PROV relations, and analysis results.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-[rgba(184,165,143,0.38)]">
        <span className="text-accent font-mono text-xs uppercase tracking-wider">
          Inspector
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggleExpand}
            className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors"
            title={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? '◀ Collapse' : '▶ Expand'}
          </button>
          <span className="text-muted font-mono text-xs">
            {selectedProvNode?.id || selectedStep?.step_id || 'none'}
          </span>
        </div>
      </div>

      {/* Match Diagnostics */}
      {matchResult && (
        <div className={`px-4 py-2 border-b border-[rgba(184,165,143,0.38)] text-[10px] font-mono flex items-center justify-between ${
          matchResult.matchType === 'exact' ? 'bg-green-50' :
          matchResult.matchType === 'fuzzy' ? 'bg-yellow-50' :
          'bg-red-50'
        }`}>
          <div className="flex items-center gap-2">
            <span className={`font-bold ${
              matchResult.matchType === 'exact' ? 'text-green-600' :
              matchResult.matchType === 'fuzzy' ? 'text-yellow-600' :
              'text-red-600'
            }`}>
              {matchResult.matchType === 'exact' ? '✓' :
               matchResult.matchType === 'fuzzy' ? '~' :
               '✗'}
            </span>
            <span className="text-muted">
              {matchResult.matchType === 'exact' ? 'Exact' :
               matchResult.matchType === 'fuzzy' ? 'Fuzzy' :
               'No'} match
            </span>
            {matchResult.similarityScore !== undefined && (
              <span className="text-muted">
                ({(matchResult.similarityScore * 100).toFixed(0)}%)
              </span>
            )}
          </div>
          <div className="text-right">
            <div className="text-muted truncate max-w-[200px]" title={matchResult.matchedKey || 'none'}>
              Artifact: {matchResult.matchedKey || 'none'}
            </div>
            <div className="text-muted truncate max-w-[200px]" title={matchResult.candidates[0] || 'none'}>
              From: {matchResult.candidates[0] || 'none'}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 p-4">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`
              px-2.5 py-1 rounded-full border font-mono text-xs cursor-pointer transition-colors
              ${activeTab === tab
                ? 'text-accent border-[rgba(37,118,184,0.55)]'
                : 'text-muted border-[rgba(184,165,143,0.58)]'
              }
            `}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto px-4 pb-4 min-w-0">
        {activeTab === 'overview' && (
          <div className="min-w-0">
            <h2 className="font-serif text-2xl mb-2.5 break-words">{title}</h2>
            <p className="text-muted leading-relaxed break-words">{summary}</p>

            {artifact && artifactKind === 'dataset' && (
              <>
                {artifact.description && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">description</b>
                    <span className="text-ink">{artifact.description}</span>
                  </div>
                )}
                {artifact.sample_data && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">data_example</b>
                    {typeof artifact.sample_data === 'object' && artifact.sample_data !== null ? (
                      <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto text-xs break-all whitespace-pre-wrap">
                        {JSON.stringify(artifact.sample_data, null, 2)}
                      </pre>
                    ) : (
                      <span className="text-ink break-words">{String(artifact.sample_data)}</span>
                    )}
                  </div>
                )}
              </>
            )}

            {artifact && artifactKind === 'script' && (
              <>
                {artifact.algorithm_purpose && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">algorithm_purpose</b>
                    <span className="text-ink">{artifact.algorithm_purpose}</span>
                  </div>
                )}
                {artifact.data_flow && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">data_flow</b>
                    <span className="text-ink">{artifact.data_flow}</span>
                  </div>
                )}
              </>
            )}

            {artifact && artifactKind === 'report' && (
              <>
                {artifact.key_findings && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">key_findings</b>
                    {Array.isArray(artifact.key_findings) ? (
                      <div className="space-y-3">
                        {artifact.key_findings.map((item, i) => {
                          if (typeof item === 'object' && item !== null && 'finding' in item) {
                            const findingItem = item as { finding: string; data?: unknown };
                            const dataJson = findingItem.data ? JSON.stringify(findingItem.data) : null;
                            return (
                              <div key={i} className="bg-[rgba(255,255,255,0.5)] border border-[rgba(184,165,143,0.3)] rounded-lg p-3">
                                <div className="text-ink font-medium mb-2">
                                  • {findingItem.finding}
                                </div>
                                {dataJson && (
                                  <div className="ml-4 text-xs text-muted font-mono break-all">
                                    {dataJson}
                                  </div>
                                )}
                              </div>
                            );
                          }
                          return (
                            <div key={i} className="text-ink">
                              {typeof item === 'object' && item !== null
                                ? JSON.stringify(item, null, 2)
                                : String(item)}
                            </div>
                          );
                        })}
                      </div>
                    ) : typeof artifact.key_findings === 'object' && artifact.key_findings !== null ? (
                      <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto text-sm">
                        {JSON.stringify(artifact.key_findings, null, 2)}
                      </pre>
                    ) : (
                      <span className="text-ink">{String(artifact.key_findings ?? '')}</span>
                    )}
                  </div>
                )}
                {artifact.answers && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">answers</b>
                    {typeof artifact.answers === 'object' ? (
                      <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto break-all whitespace-pre-wrap">
                        {JSON.stringify(artifact.answers, null, 2)}
                      </pre>
                    ) : (
                      <span className="text-ink break-words">{String(artifact.answers)}</span>
                    )}
                  </div>
                )}
              </>
            )}

            {!artifact && selectedStep && (
              <>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">operation</b>
                  <span className="text-ink">{selectedStep.operation || 'analysis_node'}</span>
                </div>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">description</b>
                  <span className="text-ink">{selectedStep.description || 'No description available'}</span>
                </div>
                {(selectedStep.input_files.length > 0 || selectedStep.output_files.length > 0) && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">files</b>
                    <div className="text-ink text-xs space-y-1">
                      {selectedStep.input_files.length > 0 && (
                        <div>
                          <span className="text-muted">inputs:</span>
                          <ul className="ml-4 list-disc">
                            {selectedStep.input_files.slice(0, 3).map((f, i) => (
                              <li key={i}>{baseName(f)}</li>
                            ))}
                            {selectedStep.input_files.length > 3 && (
                              <li className="text-muted">+{selectedStep.input_files.length - 3} more</li>
                            )}
                          </ul>
                        </div>
                      )}
                      {selectedStep.output_files.length > 0 && (
                        <div>
                          <span className="text-muted">outputs:</span>
                          <ul className="ml-4 list-disc">
                            {selectedStep.output_files.slice(0, 3).map((f, i) => (
                              <li key={i}>{baseName(f)}</li>
                            ))}
                            {selectedStep.output_files.length > 3 && (
                              <li className="text-muted">+{selectedStep.output_files.length - 3} more</li>
                            )}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {selectedStep.code_files.length > 0 && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">code files</b>
                    <ul className="text-ink text-xs list-disc ml-4">
                      {selectedStep.code_files.map((f, i) => (
                        <li key={i}>{baseName(f)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {selectedStep.commands_run && selectedStep.commands_run.length > 0 && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">commands</b>
                    <ul className="text-ink text-xs list-disc ml-4">
                      {selectedStep.commands_run.map((c, i) => (
                        <li key={i} className="break-all">{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">timestamp</b>
                  <span className="text-ink text-xs">{selectedStep.timestamp || 'unknown'}</span>
                </div>
              </>
            )}
            {!artifact && !selectedStep && selectedProvNode && (
              <>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">type</b>
                  <span className="text-ink">
                    {selectedProvNode.type} / {selectedProvNode.entity_type || selectedProvNode.activity_type || selectedProvNode.agent_type || ''}
                  </span>
                </div>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">location</b>
                  <span className="text-ink text-xs break-all">{selectedProvNode.location || 'unknown'}</span>
                </div>
                {selectedProvNode.description && (
                  <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                    <b className="block text-accent font-mono text-xs mb-2">description</b>
                    <span className="text-ink">{selectedProvNode.description}</span>
                  </div>
                )}
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">timestamp</b>
                  <span className="text-ink">{selectedProvNode.timestamp || 'unknown'}</span>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'files' && (
          <div>
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">input files</b>
              {(selectedStep?.input_files || []).map((f) => (
                <span key={f} className="text-ink block">
                  {baseName(f)}
                </span>
              )) || <span className="text-muted">—</span>}
            </div>
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">output files</b>
              {(selectedStep?.output_files || []).map((f) => (
                <span key={f} className="text-ink block">
                  {baseName(f)}
                </span>
              )) || <span className="text-muted">—</span>}
            </div>
          </div>
        )}

        {activeTab === 'code' && (
          <div>
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">code files</b>
              {(selectedStep?.code_files || []).map((f) => (
                <span key={f} className="text-ink block text-xs break-all">
                  {f}
                </span>
              )) || <span className="text-muted">—</span>}
            </div>
            {artifactKind === 'script' && artifact?.algorithm_logic && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">algorithm_logic</b>
                {Array.isArray(artifact.algorithm_logic) ? (
                  <ol className="text-ink list-decimal list-inside">
                    {artifact.algorithm_logic.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ol>
                ) : (
                  <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto">
                    {JSON.stringify(artifact.algorithm_logic, null, 2)}
                  </pre>
                )}
              </div>
            )}
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">commands</b>
              {(selectedStep?.commands_run || []).map((c) => (
                <span key={c} className="text-ink block text-xs">
                  {c}
                </span>
              )) || <span className="text-muted">—</span>}
            </div>
          </div>
        )}

        {activeTab === 'report' && artifactKind === 'report' && (
          <div>
            {artifact?.key_findings != null && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">key_findings</b>
                {Array.isArray(artifact.key_findings) ? (
                  <div className="space-y-3">
                    {artifact.key_findings.map((item: unknown, i: number) => {
                      if (typeof item === 'object' && item !== null && 'finding' in item) {
                        const findingItem = item as { finding: string; data?: unknown };
                        const dataJson = findingItem.data ? JSON.stringify(findingItem.data) : null;
                        return (
                          <div key={i} className="bg-[rgba(255,255,255,0.5)] border border-[rgba(184,165,143,0.3)] rounded-lg p-3">
                            <div className="text-ink font-medium mb-2">
                              • {findingItem.finding}
                            </div>
                            {dataJson && (
                              <div className="ml-4 text-xs text-muted font-mono break-all">
                                {dataJson}
                              </div>
                            )}
                          </div>
                        );
                      }
                      return (
                        <div key={i} className="text-ink">
                          {typeof item === 'string' ? item : JSON.stringify(item)}
                        </div>
                      );
                    })}
                  </div>
                ) : typeof artifact.key_findings === 'object' && artifact.key_findings !== null ? (
                  <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto text-sm">
                    {JSON.stringify(artifact.key_findings, null, 2)}
                  </pre>
                ) : (
                  <span className="text-ink">{String(artifact.key_findings ?? '')}</span>
                )}
              </div>
            )}
            {artifact?.answers != null && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">answers</b>
                {typeof artifact.answers === 'object' && artifact.answers !== null ? (
                  <pre className="text-ink bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 overflow-auto text-sm break-all whitespace-pre-wrap">
                    {JSON.stringify(artifact.answers, null, 2)}
                  </pre>
                ) : (
                  <span className="text-ink break-words">{String(artifact.answers ?? '')}</span>
                )}
              </div>
            )}
            {artifact?.description && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">description</b>
                <span className="text-ink">{artifact.description}</span>
              </div>
            )}
            {artifact?.key_findings == null && artifact?.answers == null && !artifact?.description && (
              <p className="text-muted text-sm">No report content available.</p>
            )}
          </div>
        )}

        {activeTab === 'echart' && (artifactKind === 'dataset' || getNodeType() === 'dataset') && (
          <div>
            {artifact?.echarts_chart ? (
              <div
                ref={setChartRef}
                className="w-full h-80 border border-[rgba(184,165,143,0.42)] rounded-xl bg-[rgba(255,255,255,0.78)]"
              />
            ) : artifact ? (
              <p className="text-muted text-sm">
                Large datasets or unsuitable for visualization, echart skipped.
              </p>
            ) : (
              <p className="text-muted text-sm">
                No artifact available for this dataset. Chart requires matching analysis artifact.
              </p>
            )}
          </div>
        )}

        {activeTab === 'parameters' && (
          <>
            {selectedStep?.parameters && Object.keys(selectedStep.parameters).length > 0 ? (
              Object.entries(selectedStep.parameters).map(([key, value]) => (
                <div key={key} className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">{key}</b>
                  <span className="text-ink break-all">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-muted text-sm">No parameters recorded.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function getArtifactKind(artifact: LlmArtifact): 'script' | 'dataset' | 'report' | null {
  if ('algorithm_purpose' in artifact || 'algorithm_logic' in artifact || 'data_flow' in artifact) {
    return 'script';
  }
  if ('sample_data' in artifact || 'echarts_echart' in artifact) {
    return 'dataset';
  }
  if ('key_findings' in artifact || 'answers' in artifact) {
    return 'report';
  }
  return null;
}
