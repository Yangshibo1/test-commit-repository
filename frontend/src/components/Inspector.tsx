import { useState, useEffect } from 'react';
import { ProvNode, StepDetail, LlmArtifact, TraceData, ArtifactMatchResult } from '../types';
import { findLlmArtifactWithDiagnostics, baseName } from '../utils/traceParser';
import * as echarts from 'echarts';

interface InspectorProps {
  selectedProvNode?: ProvNode;
  selectedStep?: StepDetail;
  trace?: TraceData;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

type InspectorTab = 'overview' | 'files' | 'code' | 'visualization' | 'report' | 'parameters' | 'run' | 'plan' | 'interventions';

export default function Inspector({ selectedProvNode, selectedStep, trace, isExpanded = false, onToggleExpand }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTab>('overview');
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
  const getAvailableTabs = (): InspectorTab[] => {
    if (trace?.sourceFormat === 'workflow') {
      return ['overview', 'files', 'code', 'run', 'plan', 'interventions'];
    }
    // 优先使用 artifactKind，如果没有则回退到节点类型
    const effectiveKind = artifactKind || getNodeType();

    if (effectiveKind === 'dataset') {
      return ['overview', 'files', 'visualization', 'parameters'];
    }
    if (effectiveKind === 'report') {
      return ['overview', 'files', 'visualization', 'report', 'parameters'];
    }
    if (effectiveKind === 'code') {
      return ['overview', 'files', 'code', 'parameters'];
    }

    // 默认 tabs（无法判断节点类型）
    return ['overview', 'files', 'parameters'];
  };

  const tabs = getAvailableTabs();

  useEffect(() => {
    if (!tabs.includes(activeTab)) setActiveTab('overview');
  }, [activeTab, selectedStep?.step_id, trace?.sourceFormat]);

  useEffect(() => {
    if (activeTab === 'visualization' && artifactKind === 'dataset' && chartRef && artifact?.echarts_chart) {
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
      {matchResult && trace?.sourceFormat !== 'workflow' && (
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
            {{
              overview: '概览',
              files: '文件',
              code: '执行',
              visualization: '可视化',
              report: '报告',
              parameters: '参数',
              run: 'Run',
              plan: 'Plan',
              interventions: '人工介入',
            }[tab]}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto px-4 pb-4 min-w-0">
        {activeTab === 'overview' && (
          <div className="min-w-0">
            <h2 className="font-serif text-2xl mb-2.5 break-words">{title}</h2>
            <p className="text-muted leading-relaxed break-words">{summary}</p>

            {trace?.sourceFormat === 'workflow' && selectedStep && (
              <div className="mt-4 space-y-3">
                <Field label="Node 状态" value={`${selectedStep.status || 'unknown'} · Plan Revision ${selectedStep.plan_version ?? '—'}`} />
                <Field label="操作说明" value={selectedStep.operation_summary || '未记录'} />
                <Field label="处理结果" value={selectedStep.result_summary || '未记录'} />
                <Field label="分析结论" value={selectedStep.analysis_conclusion || '未记录'} />
                <Field label="执行时间" value={`${selectedStep.started_at || '—'} → ${selectedStep.completed_at || '—'}`} mono />
              </div>
            )}

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

            {artifact && artifactKind === 'code' && (
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
              {(selectedStep?.input_versions?.length ? selectedStep.input_versions : (selectedStep?.input_files || []).map((path) => ({ path, sha256: '' }))).map((file) => (
                <FileVersionRow key={`${file.path}-${file.sha256}`} path={file.path} sha256={file.sha256} />
              ))}
              {!selectedStep?.input_files.length && <span className="text-muted">—</span>}
            </div>
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">output files</b>
              {(selectedStep?.output_versions?.length ? selectedStep.output_versions : (selectedStep?.output_files || []).map((path) => ({ path, sha256: '' }))).map((file) => (
                <FileVersionRow key={`${file.path}-${file.sha256}`} path={file.path} sha256={file.sha256} />
              ))}
              {!selectedStep?.output_files.length && <span className="text-muted">—</span>}
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
            {artifactKind === 'code' && artifact?.algorithm_purpose && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">algorithm_purpose</b>
                <span className="text-ink">{artifact.algorithm_purpose}</span>
              </div>
            )}
            {artifactKind === 'code' && artifact?.algorithm_logic && (
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
            {artifactKind === 'code' && artifact?.data_flow && (
              <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                <b className="block text-accent font-mono text-xs mb-2">data_flow</b>
                <span className="text-ink">{artifact.data_flow}</span>
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

        {activeTab === 'visualization' && (artifactKind === 'dataset' || artifactKind === 'report' || getNodeType() === 'dataset' || getNodeType() === 'report') && (
          <div>
            {/* HTML 可视化 */}
            {artifact?.visualization && artifact.visualization_type === 'html' && (
              <div
                className="w-full border border-[rgba(184,165,143,0.42)] rounded-xl bg-white"
                dangerouslySetInnerHTML={{ __html: artifact.visualization }}
              />
            )}

            {/* 图片可视化 */}
            {artifact?.visualization && artifact.visualization_type === 'image' && (
              <div className="w-full border border-[rgba(184,165,143,0.42)] rounded-xl bg-white p-4">
                <img
                  src={artifact.visualization}
                  alt="Visualization"
                  className="w-full h-auto rounded-lg"
                />
              </div>
            )}

            {/* ECharts 可视化（原有支持） */}
            {artifact?.echarts_chart && !artifact?.visualization && (
              <div
                ref={setChartRef}
                className="w-full h-80 border border-[rgba(184,165,143,0.42)] rounded-xl bg-[rgba(255,255,255,0.78)]"
              />
            )}

            {/* 无可视化内容 */}
            {!artifact?.visualization && !artifact?.echarts_chart && (
              <p className="text-muted text-sm">
                {artifact ? 'No visualization available for this artifact.' : 'No artifact available. Visualization requires matching analysis artifact.'}
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

        {activeTab === 'run' && trace?.run && (
          <div>
            <Field label="Run ID" value={trace.run.run_id} mono />
            <Field label="任务" value={trace.run.task} />
            <Field label="状态" value={trace.run.status} />
            <Field label="Agent / Session" value={`${trace.run.agent} / ${trace.run.session_id}`} mono />
            <Field label="项目目录" value={trace.run.project_root} mono />
            <Field label="结果目录" value={trace.run.result_root} mono />
            <Field label="开始与完成时间" value={`${trace.run.started_at} → ${trace.run.completed_at || '—'}`} mono />
            <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
              <b className="block text-accent font-mono text-xs mb-2">声明输入文件</b>
              {trace.run.declared_inputs.map((file) => <FileVersionRow key={`${file.path}-${file.sha256}`} path={file.path} sha256={file.sha256} />)}
            </div>
          </div>
        )}

        {activeTab === 'plan' && (
          <div className="space-y-3">
            {(trace?.planRevisions || []).slice().reverse().map((revision) => (
              <div key={revision.version} className="rounded-xl border border-[rgba(184,165,143,0.42)] bg-white p-3">
                <div className="flex justify-between gap-2 text-xs font-mono">
                  <b className="text-accent">Revision {revision.version}</b>
                  <span className="text-muted">{revision.trigger}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{revision.change_reason || '初始计划'}</p>
                <p className="mt-1 text-[10px] font-mono text-muted">{revision.created_at}</p>
                <div className="mt-2 space-y-2">
                  {revision.nodes.map((node) => (
                    <div key={node.node_id} className="border-t border-[rgba(184,165,143,0.3)] pt-2">
                      <div className="text-xs"><b className="font-mono text-accent">{node.node_id}</b> · {node.objective}</div>
                      <div className="mt-1 text-[10px] font-mono text-muted">依赖：{node.depends_on.join(', ') || '无'} · 产物：{node.required_artifacts.join(', ') || '未指定'}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {!trace?.planRevisions?.length && <p className="text-muted text-sm">没有 Plan Revision 记录。</p>}
          </div>
        )}

        {activeTab === 'interventions' && (
          <div className="space-y-3">
            {(trace?.humanInterventions || []).map((item) => (
              <div key={item.intervention_id} className="rounded-xl border border-[rgba(184,165,143,0.42)] bg-white p-3">
                <div className="flex justify-between gap-2 text-[10px] font-mono">
                  <b className="text-accent">{item.type}</b>
                  <span className="text-muted">Plan {item.plan_version ?? '—'}</span>
                </div>
                <p className="mt-2 text-sm leading-5">{item.original_text}</p>
                <div className="mt-2 rounded-lg bg-[#fffaf6] p-2 text-xs leading-5"><b>工作流影响：</b>{item.workflow_effect || '未记录'}</div>
                <p className="mt-2 text-[10px] font-mono text-muted">{item.created_at} → {item.applied_at || '待应用'}</p>
              </div>
            ))}
            {!trace?.humanInterventions?.length && <p className="text-muted text-sm">该 Run 没有人工介入记录。</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
      <b className="block text-accent font-mono text-xs mb-2">{label}</b>
      <span className={`text-ink break-words whitespace-pre-wrap ${mono ? 'font-mono text-xs break-all' : ''}`}>{value}</span>
    </div>
  );
}

function FileVersionRow({ path, sha256 }: { path: string; sha256: string }) {
  return (
    <div className="mb-2 rounded-lg border border-[rgba(184,165,143,0.3)] bg-white px-2.5 py-2">
      <div className="text-xs break-all">{path}</div>
      {sha256 && <div className="mt-1 text-[9px] font-mono text-muted break-all">SHA-256 · {sha256}</div>}
    </div>
  );
}

function getArtifactKind(artifact: LlmArtifact): 'code' | 'dataset' | 'report' | null {
  if ('algorithm_purpose' in artifact || 'algorithm_logic' in artifact || 'data_flow' in artifact) {
    return 'code';
  }
  if ('sample_data' in artifact || 'echarts_chart' in artifact) {
    return 'dataset';
  }
  if ('key_findings' in artifact || 'answers' in artifact) {
    return 'report';
  }
  return null;
}
