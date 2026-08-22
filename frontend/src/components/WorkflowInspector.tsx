import { FileVersion, ProvNode, StepDetail, TraceData, WorkflowIntervention } from '../types';

interface WorkflowInspectorProps {
  selectedProvNode?: ProvNode;
  selectedStep?: StepDetail;
  trace: TraceData;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  onShowRun?: () => void;
  onSelectStep?: (step: StepDetail) => void;
}

const panelClass = 'rounded-2xl border border-[rgba(184,165,143,0.42)] bg-white/70 p-4';

export default function WorkflowInspector({
  selectedProvNode,
  selectedStep,
  trace,
  isExpanded = false,
  onToggleExpand,
  onShowRun,
  onSelectStep,
}: WorkflowInspectorProps) {
  const selectedFile = selectedProvNode?.type === 'entity' ? selectedProvNode : undefined;
  const kind = selectedFile ? 'file' : selectedStep ? 'node' : 'run';
  const title = kind === 'file' ? '文件详情' : kind === 'node' ? '分析 Node' : 'Run 概览';

  return (
    <div className="h-full flex flex-col">
      <div className="min-h-12 flex items-center justify-between gap-3 px-4 py-2 border-b border-[rgba(184,165,143,0.38)] bg-white/40">
        <div>
          <div className="ot-section-title">{title}</div>
          <div className="ot-meta text-muted">
            {kind === 'run' ? '任务、计划与执行状态' : kind === 'node' ? selectedStep?.step_id : selectedFile?.entity_type || 'artifact'}
          </div>
        </div>
        <div className="flex gap-2">
          {kind !== 'run' && (
            <button className="ot-meta rounded-lg border border-line-strong bg-white px-2.5 py-1 hover:border-accent" onClick={onShowRun}>
              Run 概览
            </button>
          )}
          <button className="ot-meta rounded-lg border border-line-strong bg-white px-2.5 py-1 hover:border-accent" onClick={onToggleExpand}>
            {isExpanded ? '收起' : '展开'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {kind === 'run' && <RunOverview trace={trace} onSelectStep={onSelectStep} />}
        {kind === 'node' && selectedStep && <NodeDetails trace={trace} step={selectedStep} onSelectStep={onSelectStep} />}
        {kind === 'file' && selectedFile && <FileDetails trace={trace} file={selectedFile} onSelectStep={onSelectStep} />}
      </div>
    </div>
  );
}

function RunOverview({ trace, onSelectStep }: { trace: TraceData; onSelectStep?: (step: StepDetail) => void }) {
  const run = trace.run;
  const planRevisions = trace.planRevisions || [];
  const latestPlan = planRevisions[planRevisions.length - 1];
  const completed = trace.steps.filter((step) => step.status === 'completed').length;
  const outputCount = new Set(trace.steps.flatMap((step) => step.output_files).map(normalizePath)).size;

  return (
    <div className="space-y-4">
      <Section title="原始任务">
        <p className="ot-body whitespace-pre-wrap">{run?.task || '未记录任务描述'}</p>
      </Section>

      <div className="grid grid-cols-2 gap-3">
        <Metric label="执行状态" value={run?.status || 'unknown'} />
        <Metric label="分析结果" value={run?.analysis_outcome || 'not_assessed'} />
        <Metric label="Plan Revision" value={String(latestPlan?.version ?? '—')} />
        <Metric label="完成 Node" value={`${completed}/${trace.steps.length}`} />
        <Metric label="输出文件" value={String(outputCount)} />
      </div>

      <Section title="Run 信息">
        <KeyValue label="Run ID" value={run?.run_id || trace.sessionId} mono />
        <KeyValue label="Agent" value={run?.agent || '—'} />
        <KeyValue label="开始时间" value={formatTime(run?.started_at)} />
        <KeyValue label="完成时间" value={formatTime(run?.completed_at)} />
        <KeyValue label="结果目录" value={run?.result_root || '—'} mono />
      </Section>

      <Section title={`最新计划 · Revision ${latestPlan?.version ?? '—'}`}>
        {latestPlan?.nodes.length ? (
          <div className="space-y-2">
            {latestPlan.nodes.map((node) => {
              const actual = trace.steps.find((step) => step.step_id === node.node_id);
              return (
                <button
                  key={node.node_id}
                  disabled={!actual}
                  onClick={() => actual && onSelectStep?.(actual)}
                  className="w-full text-left rounded-xl border border-line bg-[#fffaf5] px-3 py-2 hover:border-accent disabled:cursor-default"
                >
                  <div className="flex justify-between gap-3">
                    <span className="font-mono ot-meta text-accent">{node.node_id}</span>
                    <Status value={actual?.status || 'pending'} />
                  </div>
                  <div className="ot-body font-medium mt-1">{node.objective}</div>
                  <div className="ot-meta text-muted mt-1">
                    依赖：{node.depends_on.length ? node.depends_on.join('、') : '无'}
                  </div>
                </button>
              );
            })}
          </div>
        ) : <Empty text="没有 Plan Revision" />}
      </Section>

      <details className={panelClass} open>
        <summary className="ot-section-title cursor-pointer">Plan 修订历史 ({trace.planRevisions?.length || 0})</summary>
        <div className="mt-3 space-y-3">
          {(trace.planRevisions || []).slice().reverse().map((revision) => (
            <div key={revision.version} className="border-l-2 border-accent-line pl-3">
              <div className="ot-body font-semibold">Revision {revision.version} · {revision.trigger}</div>
              <div className="ot-meta text-muted">{formatTime(revision.created_at)}</div>
              {revision.change_reason && <div className="ot-body mt-1">{revision.change_reason}</div>}
            </div>
          ))}
          {!trace.planRevisions?.length && <Empty text="没有修订记录" />}
        </div>
      </details>

      <Section title={`输入文件 (${run?.declared_inputs?.length || 0})`}>
        <FileList files={run?.declared_inputs || []} />
      </Section>

      <Section title={`人工介入 (${trace.humanInterventions?.length || 0})`}>
        <InterventionList interventions={trace.humanInterventions || []} />
      </Section>

      <Section title="记录一致性">
        {trace.consistency.ok ? (
          <p className="ot-body text-green-700">未发现结构一致性问题。</p>
        ) : (
          <ul className="space-y-2">
            {trace.consistency.warnings.map((warning) => <li key={warning} className="ot-body text-amber-700">• {warning}</li>)}
          </ul>
        )}
      </Section>
    </div>
  );
}

function NodeDetails({ trace, step, onSelectStep }: { trace: TraceData; step: StepDetail; onSelectStep?: (step: StepDetail) => void }) {
  const planRevisions = trace.planRevisions || [];
  const revision = planRevisions.find((item) => item.version === step.plan_version) || planRevisions[planRevisions.length - 1];
  const planNode = revision?.nodes.find((node) => node.node_id === step.step_id);
  const interventions = (trace.humanInterventions || []).filter((item) => item.active_node_id === step.step_id);
  const externalInputs = (step.input_versions || []).filter((file) => isExternalInput(trace, file.path));
  const upstreamInputs = (step.input_versions || []).filter((file) => !isExternalInput(trace, file.path));
  const outputs = groupFiles(step.output_versions || []);

  return (
    <div className="space-y-4">
      <Section title="Node 目标与状态">
        <div className="flex items-center justify-between gap-3 mb-2">
          <span className="font-mono ot-meta text-accent">{step.step_id} · Revision {step.plan_version ?? '—'}</span>
          <Status value={step.status || 'recorded'} />
        </div>
        <p className="ot-body font-medium">{step.name}</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <KeyValue label="开始" value={formatTime(step.started_at)} />
          <KeyValue label="完成" value={formatTime(step.completed_at)} />
        </div>
      </Section>

      <Section title="为什么执行此 Node">
        <KeyValue label="依赖 Node" value={planNode?.depends_on.length ? planNode.depends_on.join('、') : '无'} mono />
        {planNode?.depends_on.map((id) => {
          const dependency = trace.steps.find((item) => item.step_id === id);
          return dependency ? (
            <button key={id} className="ot-meta mr-2 mt-2 rounded-lg border border-line bg-[#fffaf5] px-2.5 py-1 hover:border-accent" onClick={() => onSelectStep?.(dependency)}>
              查看 {id}
            </button>
          ) : null;
        })}
        {!!interventions.length && <div className="mt-3"><InterventionList interventions={interventions} /></div>}
      </Section>

      <Section title="实际执行">
        <p className="ot-body whitespace-pre-wrap">{step.operation_summary || '未记录操作摘要'}</p>
        <details className="mt-3 rounded-xl border border-line bg-[#fffaf5] px-3 py-2">
          <summary className="ot-body font-medium cursor-pointer">命令与程序</summary>
          <div className="mt-3">
            <Label text={`命令 (${step.commands_run?.length || 0})`} />
            <MonoList values={step.commands_run || []} empty="未记录命令" />
            <Label text={`程序 (${step.code_files.length})`} />
            <MonoList values={step.code_files} empty="未记录程序文件" />
          </div>
        </details>
      </Section>

      <Section title="输入文件">
        <FileGroup title="外部输入" files={externalInputs} />
        <FileGroup title="上游 Node 产物" files={upstreamInputs} />
      </Section>

      <Section title="输出产物">
        {Object.entries(outputs).map(([type, files]) => <FileGroup key={type} title={artifactTypeLabel(type)} files={files} />)}
        {!step.output_versions?.length && <Empty text="没有记录输出文件" />}
      </Section>

      <Section title="处理结果">
        <KeyValue label="结果状态" value={step.analysis_outcome || 'not_assessed'} />
        <p className="ot-body whitespace-pre-wrap">{step.result_summary || '未记录处理结果'}</p>
      </Section>

      <Section title="阶段分析结论">
        <p className="ot-body whitespace-pre-wrap">{step.analysis_conclusion || '未记录阶段结论'}</p>
      </Section>

      {!!step.recording_warnings?.length && (
        <Section title="记录提示">
          <ul className="space-y-2">
            {step.recording_warnings.map((warning) => <li key={warning} className="ot-body text-amber-700">• {warning}</li>)}
          </ul>
        </Section>
      )}
    </div>
  );
}

function FileDetails({ trace, file, onSelectStep }: { trace: TraceData; file: ProvNode; onSelectStep?: (step: StepDetail) => void }) {
  const path = file.location || file.name || file.id;
  const lineage = trace.fileLineage || [];
  const producers = lineage.filter((item) => item.outputs.some((version) => samePath(version.path, path))).map((item) => item.node_id);
  const consumers = lineage.filter((item) => item.inputs.some((version) => samePath(version.path, path))).map((item) => item.node_id);
  const hashes = Array.from(new Set([
    ...(((file.attributes?.sha256_versions as string[] | undefined) || [])),
    ...lineage.flatMap((item) => [...item.inputs, ...item.outputs]).filter((version) => samePath(version.path, path)).map((version) => version.sha256),
  ].filter(Boolean)));
  const external = isExternalInput(trace, path) || Boolean(file.attributes?.declared_input);

  return (
    <div className="space-y-4">
      <Section title="文件身份">
        <KeyValue label="产物类型" value={artifactTypeLabel(file.entity_type || 'data')} />
        <KeyValue label="来源" value={external ? '外部输入（首次使用时登记）' : 'Node 生成产物'} />
        <div className="mt-3">
          <Label text="文件路径" />
          <div className="ot-meta font-mono break-all rounded-xl bg-[#fffaf5] border border-line px-3 py-2">{path}</div>
        </div>
      </Section>

      <Section title={`文件版本 (${hashes.length})`}>
        <MonoList values={hashes} empty="未记录 SHA-256" />
      </Section>

      <Section title="血缘关系">
        <NodeLinks title="生成者" ids={producers} trace={trace} onSelectStep={onSelectStep} empty={external ? '外部输入，没有生成 Node' : '未找到生成 Node'} />
        <NodeLinks title="使用者" ids={consumers} trace={trace} onSelectStep={onSelectStep} empty="尚未被后续 Node 使用" />
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className={panelClass}><h3 className="ot-section-title mb-3">{title}</h3>{children}</section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className={panelClass}><div className="ot-meta text-muted">{label}</div><div className="ot-stat mt-1 break-all">{value}</div></div>;
}

function KeyValue({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return <div className="grid grid-cols-[88px_1fr] gap-3 py-1.5"><div className="ot-meta text-muted">{label}</div><div className={`ot-body break-all ${mono ? 'font-mono' : ''}`}>{value || '—'}</div></div>;
}

function Label({ text }: { text: string }) {
  return <div className="ot-meta font-semibold text-muted mt-2 mb-1.5">{text}</div>;
}

function Status({ value }: { value: string }) {
  const done = value === 'completed';
  return <span className={`ot-meta rounded-full border px-2 py-0.5 ${done ? 'border-green-300 bg-green-50 text-green-700' : 'border-amber-300 bg-amber-50 text-amber-700'}`}>{value}</span>;
}

function FileList({ files }: { files: FileVersion[] }) {
  if (!files.length) return <Empty text="没有文件" />;
  return <div className="space-y-2">{files.map((file, index) => (
    <div key={`${file.path}-${index}`} className="rounded-xl border border-line bg-[#fffaf5] px-3 py-2">
      <div className="ot-meta font-mono break-all">{file.path}</div>
      {file.sha256 && <div className="ot-meta font-mono text-muted break-all mt-1">SHA {file.sha256}</div>}
    </div>
  ))}</div>;
}

function FileGroup({ title, files }: { title: string; files: FileVersion[] }) {
  return <div className="mb-3 last:mb-0"><Label text={`${title} (${files.length})`} />{files.length ? <FileList files={files} /> : <Empty text="无" />}</div>;
}

function MonoList({ values, empty }: { values: string[]; empty: string }) {
  if (!values.length) return <Empty text={empty} />;
  return <div className="space-y-2 mb-3">{values.map((value, index) => <div key={`${value}-${index}`} className="ot-meta font-mono break-all rounded-lg bg-white border border-line px-2.5 py-2">{value}</div>)}</div>;
}

function InterventionList({ interventions }: { interventions: WorkflowIntervention[] }) {
  if (!interventions.length) return <Empty text="没有人工介入" />;
  return <div className="space-y-3">{interventions.map((item) => (
    <div key={item.intervention_id} className="rounded-xl border border-amber-200 bg-amber-50/60 px-3 py-2">
      <div className="flex justify-between gap-2 ot-meta text-amber-800"><span>{item.type}</span><span>{formatTime(item.created_at)}</span></div>
      <div className="ot-body mt-1 whitespace-pre-wrap">{item.original_text}</div>
      {item.workflow_effect && <div className="ot-meta text-muted mt-1">影响：{item.workflow_effect}</div>}
    </div>
  ))}</div>;
}

function NodeLinks({ title, ids, trace, onSelectStep, empty }: { title: string; ids: string[]; trace: TraceData; onSelectStep?: (step: StepDetail) => void; empty: string }) {
  const unique = Array.from(new Set(ids));
  return <div className="mb-4 last:mb-0"><Label text={`${title} (${unique.length})`} />{unique.length ? <div className="flex flex-wrap gap-2">{unique.map((id) => {
    const step = trace.steps.find((item) => item.step_id === id);
    return <button key={id} className="ot-meta font-mono rounded-lg border border-line bg-[#fffaf5] px-2.5 py-1 hover:border-accent" onClick={() => step && onSelectStep?.(step)}>{id}</button>;
  })}</div> : <Empty text={empty} />}</div>;
}

function Empty({ text }: { text: string }) {
  return <div className="ot-meta text-muted">{text}</div>;
}

function groupFiles(files: FileVersion[]): Record<string, FileVersion[]> {
  return files.reduce<Record<string, FileVersion[]>>((groups, file) => {
    const type = artifactType(file.path);
    (groups[type] ||= []).push(file);
    return groups;
  }, {});
}

function artifactType(path: string): string {
  const value = normalizePath(path);
  if (value.includes('/code/') || /\.(py|r|sql|ipynb)$/.test(value)) return 'code';
  if (value.includes('/report/') || /\.(md|txt|pdf|docx)$/.test(value)) return 'report';
  if (value.includes('/visualization/') || /\.(html|png|jpg|jpeg|svg)$/.test(value)) return 'visualization';
  return 'data';
}

function artifactTypeLabel(type: string): string {
  return ({ code: '代码', data: '数据', report: '报告', visualization: '可视化' } as Record<string, string>)[type] || type;
}

function isExternalInput(trace: TraceData, path: string): boolean {
  const declared = trace.run?.declared_inputs?.some((item) => samePath(item.path, path));
  const generated = trace.fileLineage?.some((item) => item.outputs.some((output) => samePath(output.path, path)));
  return Boolean(declared || !generated);
}

function samePath(left: string, right: string): boolean {
  return normalizePath(left) === normalizePath(right);
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/\.\//g, '/').trim().toLowerCase();
}

function formatTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
