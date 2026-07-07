import { useState, useEffect } from 'react';
import { ProvNode, StepDetail, LlmArtifact, TraceData } from '../types';
import { findLlmArtifact, baseName } from '../utils/traceParser';
import * as echarts from 'echarts';

interface InspectorProps {
  selectedProvNode?: ProvNode;
  selectedStep?: StepDetail;
  trace?: TraceData;
}

export default function Inspector({ selectedProvNode, selectedStep, trace }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'files' | 'code' | 'chart' | 'parameters'>('overview');
  const [chartRef, setChartRef] = useState<HTMLDivElement | null>(null);

  const artifact = trace ? findLlmArtifact(trace, { step: selectedStep, node: selectedProvNode }) : null;
  const artifactKind = artifact ? getArtifactKind(artifact) : null;

  useEffect(() => {
    if (activeTab === 'chart' && artifactKind === 'dataset' && chartRef && artifact?.echarts_chart) {
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

  const title = selectedProvNode?.description || selectedProvNode?.name || selectedStep?.name || 'Selection';
  const summary = selectedStep?.description || selectedProvNode?.location || '';

  const tabs = artifactKind === 'dataset'
    ? ['overview', 'files', 'chart', 'parameters'] as const
    : ['overview', 'files', 'code', 'parameters'] as const;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-[rgba(184,165,143,0.38)]">
        <span className="text-accent font-mono text-xs uppercase tracking-wider">
          Inspector
        </span>
        <span className="text-muted font-mono text-xs">
          {selectedProvNode?.id || selectedStep?.step_id || 'none'}
        </span>
      </div>

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
      <div className="flex-1 overflow-auto px-4 pb-4">
        {activeTab === 'overview' && (
          <div>
            <h2 className="font-serif text-2xl mb-2.5">{title}</h2>
            <p className="text-muted leading-relaxed">{summary}</p>

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

            {!artifact && (
              <>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">type</b>
                  <span className="text-ink">
                    {selectedProvNode
                      ? `${selectedProvNode.type} / ${selectedProvNode.entity_type || selectedProvNode.activity_type || selectedProvNode.agent_type || ''}`
                      : selectedStep?.operation}
                  </span>
                </div>
                <div className="border-t border-[rgba(184,165,143,0.36)] py-3">
                  <b className="block text-accent font-mono text-xs mb-2">timestamp</b>
                  <span className="text-ink">
                    {selectedProvNode?.timestamp || selectedStep?.timestamp || 'unknown'}
                  </span>
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

        {activeTab === 'chart' && artifactKind === 'dataset' && (
          <div>
            {artifact?.echarts_chart ? (
              <div
                ref={setChartRef}
                className="w-full h-80 border border-[rgba(184,165,143,0.42)] rounded-xl bg-[rgba(255,255,255,0.78)]"
              />
            ) : (
              <p className="text-muted text-sm">
                Large datasets or unsuitable for visualization, chart skipped.
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
  if ('sample_data' in artifact || 'echarts_chart' in artifact) {
    return 'dataset';
  }
  if ('key_findings' in artifact || 'answers' in artifact) {
    return 'report';
  }
  return null;
}
