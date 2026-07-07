import { useState, useCallback, useRef } from 'react';
import TraceGraph, { TraceGraphRef } from './components/TraceGraph';
import Timeline from './components/Timeline';
import Inspector from './components/Inspector';
import FollowPanel from './components/FollowPanel';
import { TraceData, ProvNode, StepDetail, SessionFiles } from './types';
import { parseSessionFiles, buildProvDAGFlow } from './utils/traceParser';

const DEFAULT_WORKSPACE = 'C:\\Users\\83734\\Desktop\\opentrace\\test-commit-repository';

function App() {
  const [trace, setTrace] = useState<TraceData | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [selectedProvId, setSelectedProvId] = useState<string | null>(null);
  const [followPanelOpen, setFollowPanelOpen] = useState(false);
  const traceGraphRef = useRef<TraceGraphRef>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    const loaded: SessionFiles = {};

    for (const file of files) {
      // 使用文件名（不含路径）作为键名
      const name = file.name;
      if (!name.endsWith('.json')) continue;
      if (name === 'working_data.json') continue;

      try {
        const text = await file.text();
        loaded[name] = JSON.parse(text);
        console.log(`Loaded file: ${name}`);
      } catch (error) {
        console.error(`Failed to parse ${name}:`, error);
      }
    }

    console.log('Total files loaded:', Object.keys(loaded).length);
    console.log('File keys:', Object.keys(loaded));

    const parsed = parseSessionFiles(loaded);
    if (parsed) {
      setTrace(parsed);
      setSelectedStepId(parsed.steps[0]?.step_id || null);
      setSelectedProvId(null);
    } else {
      console.error('Failed to parse session files');
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
    setCurrentPage(0);
    setTotalPages(1);
  }, []);

  const handlePageChange = useCallback((page: number, total: number) => {
    setCurrentPage(page);
    setTotalPages(total);
  }, []);

  const selectedStep = trace?.steps.find((s) => s.step_id === selectedStepId);
  const selectedProvNode = trace?.prov.nodes[selectedProvId || ''];

  const flow = trace ? buildProvDAGFlow(trace) : { nodes: [], edges: [] };

  const selectedContext = trace ? {
    opentrace_session: trace.sessionId,
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
    <div className="h-screen flex flex-col">
      {/* Top Bar */}
      <header className="h-[92px] flex items-center px-6 border-b border-[rgba(184,165,143,0.55)] bg-[rgba(255,250,240,0.78)] backdrop-blur-2xl">
        <div className="flex items-center gap-4 flex-1">
          <div className="w-12 h-12 border border-[rgba(217,119,69,0.42)] rounded-xl flex items-center justify-center bg-gradient-to-br from-white to-[#fff6ef] shadow-lg">
            <span className="text-accent font-bold text-lg rotate-[-4deg]">OT</span>
          </div>
          <div>
            <h1 className="font-serif text-2xl leading-none">OpenTrace Workbench</h1>
            <div className="text-muted text-xs font-mono mt-1">
              {trace ? `${trace.sessionId} · created ${trace.createdAt}` : 'Load OpenTrace session folder to view PROV DAG with analysis results'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className={`
            px-3 py-2 rounded-full text-xs font-mono
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
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] text-xs font-mono cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px"
          >
            Load session folder
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
            onClick={() => setFollowPanelOpen(true)}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] text-xs font-mono cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px"
          >
            Ask follow-up
          </button>

          <button
            onClick={handleClear}
            className="px-3.5 py-2.5 rounded-full border border-[rgba(217,119,69,0.28)] text-ink bg-[rgba(255,255,255,0.9)] text-xs font-mono cursor-pointer hover:border-accent transition-all shadow-[0_8px_20px_rgba(76,55,32,0.06)] hover:-translate-y-px"
          >
            Clear
          </button>
        </div>
      </header>

      {/* Main Content */}
      <section className="flex-1 grid grid-cols-[320px_minmax(620px,1fr)_400px] gap-3.5 p-3.5 min-h-0">
        {/* Timeline */}
        <aside className="min-h-0 border border-[rgba(184,165,143,0.48)] rounded-3xl bg-panel shadow-lg overflow-hidden backdrop-blur-2xl">
          <div className="h-12 flex items-center px-4 border-b border-[rgba(184,165,143,0.38)] text-accent font-mono text-xs uppercase tracking-wider bg-[rgba(255,255,255,0.42)]">
            Trace Timeline <span className="ml-1">{trace?.steps.length || 0}</span>
          </div>
          {trace ? (
            <Timeline
              steps={trace.steps}
              selectedStepId={selectedStepId || undefined}
              onStepSelect={handleStepSelect}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
              Select a complete OpenTrace session folder, the page will automatically read the required JSON files.
            </div>
          )}
        </aside>

        {/* Graph + Funnel */}
        <section className="min-h-0 grid grid-rows-[124px_1fr] gap-3.5">
          {/* Funnel */}
          <div className="grid grid-cols-4 gap-2.5 p-3.5 border border-[rgba(184,165,143,0.42)] rounded-3xl bg-[rgba(255,255,255,0.7)]">
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="font-serif font-bold text-2xl">{trace?.steps.length || 0}</div>
              <div className="text-muted text-[11px] font-mono mt-1.5">analysis steps</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="font-serif font-bold text-2xl">{trace?.counts.entities || 0}</div>
              <div className="text-muted text-[11px] font-mono mt-1.5">PROV entities</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="font-serif font-bold text-2xl">{trace?.counts.activities || 0}</div>
              <div className="text-muted text-[11px] font-mono mt-1.5">PROV activities</div>
            </div>
            <div className="border border-[rgba(184,165,143,0.42)] rounded-2xl p-3.5 bg-[rgba(255,255,255,0.7)]">
              <div className="font-serif font-bold text-2xl">{trace?.counts.artifacts || 0}</div>
              <div className="text-muted text-[11px] font-mono mt-1.5">analysis artifacts</div>
            </div>
          </div>

          {/* Graph */}
          <div className="border border-[rgba(184,165,143,0.42)] rounded-3xl overflow-hidden bg-panel shadow-lg">
            <div className="h-12 flex items-center justify-between px-4 border-b border-[rgba(184,165,143,0.38)] text-accent font-mono text-xs uppercase tracking-wider bg-[rgba(255,255,255,0.42)]">
              <span>PROV DAG + Analysis Results</span>
              {trace && (
                <div className="flex items-center gap-2">
                  {totalPages > 1 && (
                    <>
                      <button
                        onClick={() => traceGraphRef.current?.goToPage(currentPage - 1)}
                        disabled={currentPage === 0}
                        className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        ◀
                      </button>
                      <span className="text-[10px] font-mono text-[#6b5b4f]">
                        {currentPage + 1}/{totalPages}
                      </span>
                      <button
                        onClick={() => traceGraphRef.current?.goToPage(currentPage + 1)}
                        disabled={currentPage === totalPages - 1}
                        className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        ▶
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => traceGraphRef.current?.toggleFullscreen()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors"
                    title="Fullscreen"
                  >
                    ⛶
                  </button>
                  <button
                    onClick={() => traceGraphRef.current?.zoomOut()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors"
                  >
                    −
                  </button>
                  <button
                    onClick={() => traceGraphRef.current?.zoomIn()}
                    className="px-2 py-1 rounded border border-[rgba(184,165,143,0.38)] bg-white text-[10px] font-mono hover:border-accent transition-colors"
                  >
                    +
                  </button>
                </div>
              )}
            </div>
            {trace ? (
              <TraceGraph
                ref={traceGraphRef}
                provNodes={flow.nodes}
                provEdges={flow.edges}
                onNodeClick={handleNodeClick}
                onPageChange={handlePageChange}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-muted text-sm p-8 text-center">
                Graph will be built from prov_nodes.json + prov_edges.json after loading session, and will attempt to merge final report / report parameter analysis results.
              </div>
            )}
          </div>
        </section>

        {/* Inspector */}
        <aside className="min-h-0 border border-[rgba(184,165,143,0.48)] rounded-3xl bg-panel shadow-lg overflow-hidden backdrop-blur-2xl">
          <Inspector
            selectedProvNode={selectedProvNode}
            selectedStep={selectedStep}
            trace={trace || undefined}
          />
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
  return trace.steps.find((step) =>
    hay.includes(step.step_id.toLowerCase()) ||
    step.output_files.some((f) => hay.includes(f.toLowerCase())) ||
    step.input_files.some((f) => hay.includes(f.toLowerCase()))
  );
}

export default App;
