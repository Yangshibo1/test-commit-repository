import { useState, useCallback, useRef, useMemo } from 'react';
import TraceGraph, { TraceGraphRef } from './components/TraceGraph';
import Timeline from './components/Timeline';
import Inspector from './components/Inspector';
import WorkflowInspector from './components/WorkflowInspector';
import FollowPanel from './components/FollowPanel';
import { TraceData, ProvNode, StepDetail, SessionFiles } from './types';
import { parseSessionFiles, buildProvDAGFlow } from './utils/traceParser';

const DEFAULT_WORKSPACE = 'C:\\path\\to\\analysis-project';

function App() {
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedProvId, setSelectedProvId] = useState<string | null>(null);
  const [followPanelOpen, setFollowPanelOpen] = useState(false);
  const traceGraphRef = useRef<TraceGraphRef>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [inspectorExpanded, setInspectorExpanded] = useState(false);
  const [graphView, setGraphView] = useState<'semantic' | 'lineage'>('semantic');

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    setIsLoading(true);
    setLoadError(null);

    try {
      const loaded: SessionFiles = {};
      let fileCount = 0;

      for (const file of files) {
        const name = file.name;
        if (!name.endsWith('.json')) continue;
        if (name === 'working_data.json') continue;

        try {
          const text = await file.text();
          const parsedJson = JSON.parse(text);
          if (
            parsedJson
            && typeof parsedJson === 'object'
            && parsedJson.run
            && Array.isArray(parsedJson.plan_revisions)
            && Array.isArray(parsedJson.nodes)
          ) {
            loaded['workflow.json'] = parsedJson;
          } else {
            loaded[name] = parsedJson;
          }
          fileCount++;
          console.log(`Loaded file: ${name}`);
        } catch (error) {
          console.error(`Failed to parse ${name}:`, error);
        }
      }

      console.log('Total files loaded:', fileCount);
      console.log('File keys:', Object.keys(loaded));

      if (fileCount === 0) {
        setLoadError('没有找到可用的 JSON。请选择包含 workflow.json 的 Run 结果目录。');
        setIsLoading(false);
        return;
      }

      const parsed = parseSessionFiles(loaded);
      if (parsed) {
        setTrace(parsed);
        setSelectedStepId(null);
        setSelectedProvId(null);
        setGraphView(parsed.sourceFormat === 'workflow' ? 'semantic' : 'lineage');
      } else {
        setLoadError('无法解析记录文件，请检查 workflow.json 格式。');
      }
    } catch (error) {
      console.error('Upload error:', error);
      setLoadError(`Error loading files: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fileInputRef = useCallback((input: HTMLInputElement | null) => {
    if (input) {
      input.setAttribute('webkitdirectory', '');
      input.setAttribute('directory', '');
    }
  }, []);

  const handleStepSelect = useCallback((step: StepDetail) => {
    setSelectedStepId(step.step_id);
    setSelectedProvId(null);
  }, []);

  const handleNodeClick = useCallback((node: ProvNode) => {
    // Use original_id if available (for merged nodes from buildProvDAGFlow)
    const nodeId = node.original_ids?.[0] || node.id;
    setSelectedProvId(nodeId);
    if (trace) {
      const step = findStepForProvNode(trace, nodeId);
      if (step) {
        setSelectedStepId(step.step_id);
      }
    }
  }, [trace]);

  const handleClear = useCallback(() => {
    setTrace(null);
    setSelectedStepId(null);
    setSelectedProvId(null);
    const fileInput = document.getElementById('fileInput') as HTMLInputElement;
    if (fileInput) fileInput.value = '';
    const workflowInput = document.getElementById('workflowInput') as HTMLInputElement;
    if (workflowInput) workflowInput.value = '';
    setCurrentPage(0);
    setTotalPages(1);
    setGraphView('semantic');
  }, []);

  const handlePageChange = useCallback((page: number, total: number) => {
    setCurrentPage(page);
    setTotalPages(total);
  }, []);

  const selectedStep = trace?.steps.find((s) => s.step_id === selectedStepId);
  const selectedProvNode = trace?.prov.nodes[selectedProvId || ''];

  const flow = useMemo(() => {
    if (!trace) return { nodes: [], edges: [] };
    try {
      const complete = buildProvDAGFlow(trace);
      if (trace.sourceFormat !== 'workflow' || graphView === 'lineage') return complete;
      const semanticIds = new Set(
        complete.nodes
          .filter((node) => node.agent_type === 'semantic_node')
          .map((node) => node.id),
      );
      return {
        nodes: complete.nodes.filter((node) => semanticIds.has(node.id)),
        edges: complete.edges.filter((edge) => (
          edge.relation === 'depends_on' && semanticIds.has(edge.from) && semanticIds.has(edge.to)
        )),
      };
    } catch (error) {
      console.error('buildProvDAGFlow error:', error);
      return { nodes: [], edges: [] };
    }
  }, [trace, graphView]);

  const showRunOverview = useCallback(() => {
    setSelectedStepId(null);
    setSelectedProvId(null);
  }, []);

  const changeGraphView = useCallback((view: 'semantic' | 'lineage') => {
    setGraphView(view);
    setSelectedProvId(null);
    setSelectedStepId(null);
    setCurrentPage(0);
  }, []);

  const selectedContext = trace ? {
    agentvast_session: trace.sessionId,
    selected_step: selectedStep ? {
      id: selectedStep.step_id,
      name: selectedStep.name,
      input_files: selectedStep.input_files,
      output_files: selectedStep.output_files,
      code_files: selectedStep.code_files,
    } : undefined,
    selected_node: selectedProvNode ? {
      id: selectedProvNode.id,
      type: selectedProvNode.type,
      location: selectedProvNode.location,
      name: selectedProvNode.name,
      description: selectedProvNode.description,
    } : undefined,
    analysis_artifact: undefined, // Can be added later
  } : undefined;

  return (
    <div className="record-page h-full flex flex-col">
      {/* Top Bar */}
      <header className="h-[92px] flex items-center px-6 border-b border-[rgba(184,165,143,0.55)] bg-[rgba(255,250,240,0.78)] backdrop-blur-2xl">
        <div className="flex items-center gap-4 flex-1">
          <div className="w-12 h-12 border border-[rgba(217,119,69,0.42)] rounded-xl flex items-center justify-center bg-gradient-to-br from-white to-[#fff6ef] shadow-lg">
            <span className="text-accent font-bold text-lg rotate-[-4deg]">AV</span>
          </div>
          <div>
            <h1 className="ot-page-title">AgentVAST Workbench</h1>
            <div className="text-muted ot-meta font-mono mt-1">
              {trace
                ? `${trace.sessionId} · ${trace.run?.status || 'loaded'} · schema ${trace.schemaVersion || 'legacy'}`
                : '加载 Run 结果目录，查看语义 Node、文件血缘与分析结论'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className={`
            px-3 py-2 rounded-full ot-meta font-mono
            ${trace?.consistency.ok
              ? 'text-green-600 bg-[rgba(61,143,96,0.08)] border border-[rgba(61,143,96,0.32)]'
              : 'text-amber-600 bg-[rgba(217,119,69,0.08)] border border-[rgba(217,119,69,0.32)]'
            }
          `}>
            {trace ? (trace.consistency.ok ? 'SCHEMA CONSISTENT' : 'CHECK WARNINGS') : 'WAITING FOR SESSION'}
          </span>

          <button
            onClick={() => {
              const input = document.getElementById('fileInput') as HTMLInputElement;
              input?.click();
            }}
            disabled={isLoading}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] ot-meta cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? '正在加载…' : '加载 Run 目录'}
          </button>
          <input
            id="fileInput"
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileUpload}
          />

          <button
            onClick={() => {
              const input = document.getElementById('workflowInput') as HTMLInputElement;
              input?.click();
            }}
            disabled={isLoading}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] ot-meta cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px disabled:opacity-50 disabled:cursor-not-allowed"
          >
            加载记录 JSON
          </button>
          <input
            id="workflowInput"
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={handleFileUpload}
          />

          <button
            onClick={() => setFollowPanelOpen(true)}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] ot-meta cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px"
          >
            Ask follow-up
          </button>

          <button
            onClick={handleClear}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] ot-meta cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px"
          >
            Clear
          </button>
        </div>
      </header>

      {/* Main Content */}
      <section className={inspectorExpanded
        ? "flex-1 grid grid-cols-[320px_1fr] gap-3.5 p-3.5 min-h-0"
        : "flex-1 grid grid-cols-[320px_minmax(620px,1fr)_400px] gap-3.5 p-3.5 min-h-0"
      }>
        {/* Timeline */}
        <aside className="min-h-0 border border-[rgba(184,165,143,0.48)] rounded-3xl bg-panel shadow-lg overflow-hidden backdrop-blur-2xl">
          <div className="h-12 flex items-center px-4 border-b border-[rgba(184,165,143,0.38)] text-accent ot-meta font-semibold bg-[rgba(255,255,255,0.42)]">
            语义 Node 时间线 <span className="ml-1">{trace?.steps.length || 0}</span>
          </div>
          {trace ? (
            <Timeline
              steps={trace.steps}
              selectedStepId={selectedStepId || undefined}
              interventionNodeIds={(trace.humanInterventions || []).flatMap((item) => item.active_node_id ? [item.active_node_id] : [])}
              onStepSelect={handleStepSelect}
            />
          ) : loadError ? (
            <div className="h-full flex flex-col items-center justify-center text-red-600 text-sm p-8 text-center">
              <p className="mb-2">记录加载失败：</p>
              <p className="text-muted">{loadError}</p>
            </div>
          ) : isLoading ? (
            <div className="h-full flex items-center justify-center text-accent text-sm p-8 text-center">
              正在读取记录文件…
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
              请选择包含 workflow.json 的 result/run_xxx 目录；旧版多 JSON 记录仍可兼容读取。
            </div>
          )}
        </aside>

        {/* Graph + Funnel */}
        {!inspectorExpanded && (
        <section className="min-h-0 grid grid-rows-[124px_1fr] gap-3.5">
          {/* Funnel */}
          <div className="grid grid-cols-4 gap-2.5 p-3.5 border border-[rgba(184,165,143,0.42)] rounded-3xl bg-[rgba(255,255,255,0.7)]">
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="ot-stat">{trace?.steps.length || 0}</div>
              <div className="text-muted ot-meta mt-1.5">语义 Nodes</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="ot-stat">{trace?.counts.artifacts || 0}</div>
              <div className="text-muted ot-meta mt-1.5">输出文件</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="ot-stat">{trace?.planRevisions?.length ?? trace?.counts.activities ?? 0}</div>
              <div className="text-muted ot-meta mt-1.5">Plan Revisions</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="ot-stat">{trace?.humanInterventions?.length ?? trace?.counts.edges ?? 0}</div>
              <div className="text-muted ot-meta mt-1.5">人工介入</div>
            </div>
          </div>

          {/* Graph */}
          <div className="border border-[rgba(184,165,143,0.42)] rounded-3xl overflow-hidden bg-panel shadow-lg">
            <div className="min-h-12 flex items-center justify-between gap-3 px-4 py-2 border-b border-[rgba(184,165,143,0.38)] bg-[rgba(255,255,255,0.42)]">
              <div className="flex items-center gap-3">
                <span className="ot-section-title">工作流图</span>
                {trace?.sourceFormat === 'workflow' && (
                  <div className="flex rounded-xl border border-line-strong bg-white p-1">
                    <button onClick={() => changeGraphView('semantic')} className={`ot-meta rounded-lg px-3 py-1 ${graphView === 'semantic' ? 'bg-accent text-white' : 'text-muted hover:text-ink'}`}>语义流程</button>
                    <button onClick={() => changeGraphView('lineage')} className={`ot-meta rounded-lg px-3 py-1 ${graphView === 'lineage' ? 'bg-accent text-white' : 'text-muted hover:text-ink'}`}>文件血缘</button>
                  </div>
                )}
              </div>
              {trace && (
                <div className="flex items-center gap-2">
                  {totalPages > 1 && (
                    <>
                      <button
                        onClick={() => traceGraphRef.current?.goToPage(currentPage - 1)}
                        disabled={currentPage === 0}
                        className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white ot-meta font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        ◀
                      </button>
                      <span className="ot-meta font-mono text-[#6b5b4f]">
                        {currentPage + 1}/{totalPages}
                      </span>
                      <button
                        onClick={() => traceGraphRef.current?.goToPage(currentPage + 1)}
                        disabled={currentPage === totalPages - 1}
                        className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white ot-meta font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        ▶
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => traceGraphRef.current?.toggleFullscreen()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white ot-meta font-mono hover:border-accent transition-colors"
                    title="Fullscreen"
                  >
                    ⛶
                  </button>
                  <button
                    onClick={() => traceGraphRef.current?.zoomOut()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white ot-meta font-mono hover:border-accent transition-colors"
                  >
                    −
                  </button>
                  <button
                    onClick={() => traceGraphRef.current?.zoomIn()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white ot-meta font-mono hover:border-accent transition-colors"
                  >
                    +
                  </button>
                </div>
              )}
            </div>
            {trace ? (
              <TraceGraph
                key={graphView}
                ref={traceGraphRef}
                provNodes={flow.nodes}
                provEdges={flow.edges}
                onNodeClick={handleNodeClick}
                onPageChange={handlePageChange}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
                加载 workflow.json 后，将依据最新 Plan 的 Node 依赖和真实输入输出文件生成 DAG。
              </div>
            )}
          </div>
        </section>
        )}

        {/* Inspector */}
        <aside className={inspectorExpanded
          ? "min-h-0 border border-[rgba(184,165,143,0.48)] rounded-3xl bg-panel shadow-lg overflow-hidden backdrop-blur-2xl col-span-1"
          : "min-h-0 border border-[rgba(184,165,143,0.48)] rounded-3xl bg-panel shadow-lg overflow-hidden backdrop-blur-2xl"
        }>
          {trace?.sourceFormat === 'workflow' ? (
            <WorkflowInspector
              selectedProvNode={selectedProvNode}
              selectedStep={selectedStep}
              trace={trace}
              isExpanded={inspectorExpanded}
              onToggleExpand={() => setInspectorExpanded(prev => !prev)}
              onShowRun={showRunOverview}
              onSelectStep={handleStepSelect}
            />
          ) : (
            <Inspector
              selectedProvNode={selectedProvNode}
              selectedStep={selectedStep}
              trace={trace || undefined}
              isExpanded={inspectorExpanded}
              onToggleExpand={() => setInspectorExpanded(prev => !prev)}
            />
          )}
        </aside>
      </section>

      {/* Follow Panel */}
      <FollowPanel
        isOpen={followPanelOpen}
        onClose={() => setFollowPanelOpen(false)}
        selectedContext={selectedContext}
        DEFAULT_WORKSPACE={DEFAULT_WORKSPACE}
      />
    </div>
  );
}

function findStepForProvNode(trace: TraceData, provId: string): StepDetail | undefined {
  const node = trace.prov.nodes[provId];
  if (!node) return undefined;

  const hay = `${node.location || ''} ${node.description || ''} ${node.name || ''}`.toLowerCase();
  const semanticNodeId = typeof node.attributes?.node_id === 'string'
    ? node.attributes.node_id
    : null;
  if (semanticNodeId) {
    return trace.steps.find((step) => step.step_id === semanticNodeId);
  }
  return trace.steps.find((step) =>
    hay.includes(step.step_id.toLowerCase()) ||
    step.output_files.some((f) => hay.includes(f.toLowerCase())) ||
    step.input_files.some((f) => hay.includes(f.toLowerCase()))
  );
}

export default App;
