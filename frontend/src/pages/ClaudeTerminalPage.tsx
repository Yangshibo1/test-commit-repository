import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ClaudeTerminal, {
  ClaudeTerminalHandle,
  SocketState,
  TerminalProcessStatus,
} from '../components/ClaudeTerminal';

const FALLBACK_PROJECT = '';

interface PlanNode {
  node_id: string;
  objective: string;
  depends_on: string[];
  required_artifacts: string[];
  status: 'pending' | 'active' | 'completed';
}

interface WorkflowState {
  run: {
    run_id: string;
    task_description: string;
    status: 'active' | 'completed' | 'aborted' | 'failed';
    result_root: string;
    awaiting_user: number;
    checkpoint_kind: string | null;
    checkpoint_mode: string;
    plan_approved_version: number | null;
    phase?: 'planning' | 'plan_review' | 'node_review' | 'checkpoint' | 'ready' | 'executing' | 'handling_input' | 'idle' | 'completed' | 'aborted' | 'failed';
  };
  plan: {
    version: number;
    trigger: string;
    change_reason: string | null;
    nodes: PlanNode[];
  } | null;
  nodes: Array<PlanNode & { result_summary?: string; analysis_conclusion?: string }>;
  pending_user_inputs: Array<{
    input_event_id: string;
    original_text: string;
    type: string | null;
    status: string;
  }>;
}

type InterventionType = 'challenge' | 'planning_input' | 'analysis_guidance';

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown error';
}

async function responseJson(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return body;
}

function ClaudeTerminalPage() {
  const terminalRef = useRef<ClaudeTerminalHandle | null>(null);
  const trackedRunIdRef = useRef<string | null>(null);
  const displayedRunIdRef = useRef<string | null>(null);
  const planScrollRef = useRef<HTMLDivElement | null>(null);
  const projectRootEditedRef = useRef(false);
  const [projectRoot, setProjectRoot] = useState(FALLBACK_PROJECT);
  const [defaultProjectRoot, setDefaultProjectRoot] = useState(FALLBACK_PROJECT);
  const [claudeCommand, setClaudeCommand] = useState('claude');
  const [backendState, setBackendState] = useState<'checking' | 'online' | 'offline'>('checking');
  const [socketState, setSocketState] = useState<SocketState>('idle');
  const [process, setProcess] = useState<TerminalProcessStatus | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [recoveryClaudeSessionId, setRecoveryClaudeSessionId] = useState<string | null>(null);
  const [initialTask, setInitialTask] = useState('');
  const [initialInputFiles, setInitialInputFiles] = useState('');
  const [newTraceTask, setNewTraceTask] = useState('');
  const [newTraceInputFiles, setNewTraceInputFiles] = useState('');
  const [interventionType, setInterventionType] = useState<InterventionType>('planning_input');
  const [intervention, setIntervention] = useState('');
  const [editingPlan, setEditingPlan] = useState(false);
  const [planDraft, setPlanDraft] = useState<PlanNode[]>([]);
  const [planChangeReason, setPlanChangeReason] = useState('');
  const [planRevisionRequest, setPlanRevisionRequest] = useState('');
  const [newTraceOpen, setNewTraceOpen] = useState(false);
  const [waitingPlanRevision, setWaitingPlanRevision] = useState<{ runId: string; baseVersion: number } | null>(null);
  const [planNotice, setPlanNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetPlanModule = useCallback(() => {
    setEditingPlan(false);
    setPlanDraft([]);
    setPlanChangeReason('');
    setPlanRevisionRequest('');
    setWaitingPlanRevision(null);
    setPlanNotice(null);
  }, []);

  const resetComposer = useCallback(() => {
    setNewTraceOpen(false);
    setNewTraceTask('');
    setNewTraceInputFiles('');
    setIntervention('');
  }, []);

  const refresh = useCallback(async () => {
    try {
      const health = await responseJson(await fetch('/api/health'));
      if (!Array.isArray(health.capabilities) || !health.capabilities.includes('finish_trace')) {
        throw new Error('后端版本过旧，请关闭旧服务后重新运行“启动AgentVAST.bat”');
      }
      setBackendState('online');
      const backendDefaultProject = String(health.default_project || '').trim();
      setDefaultProjectRoot(backendDefaultProject);
      setProjectRoot((current) => (
        !projectRootEditedRef.current || !current.trim()
          ? backendDefaultProject
          : current
      ));
      const status = await responseJson(await fetch('/api/terminal'));
      setProcess(status.session ?? null);
      const current = await responseJson(await fetch('/api/runs/current'));
      if (current.state) {
        const nextTrackedRunId = current.state.run.status === 'active' ? current.state.run.run_id : null;
        trackedRunIdRef.current = nextTrackedRunId;
        setWorkflow(current.state);
        setTrackedRunId(nextTrackedRunId);
        if (!current.state.plan) resetPlanModule();
        setRecoveryClaudeSessionId(current.run?.claude_session_id ?? null);
      } else {
        trackedRunIdRef.current = null;
        setWorkflow(null);
        setTrackedRunId(null);
        resetPlanModule();
        setRecoveryClaudeSessionId(null);
      }
      setError(null);
    } catch (caught) {
      setBackendState('offline');
      setError(`AgentVAST 本地服务不可用：${errorMessage(caught)}`);
    }
  }, [resetPlanModule]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    const nextRunId = workflow?.run.run_id ?? null;
    if (displayedRunIdRef.current !== nextRunId) {
      displayedRunIdRef.current = nextRunId;
      resetPlanModule();
      resetComposer();
    }
  }, [resetComposer, resetPlanModule, workflow?.run.run_id]);

  useEffect(() => {
    if (!trackedRunId) return;
    const source = new EventSource(`/api/runs/${trackedRunId}/events`);
    const update = (event: MessageEvent) => {
      try {
        const next = JSON.parse(event.data) as WorkflowState;
        if (next.run.run_id !== trackedRunIdRef.current) return;
        setWorkflow(next);
        if (next.run.status !== 'active') {
          trackedRunIdRef.current = null;
          setTrackedRunId(null);
        }
      } catch {
        setError('AgentVAST 返回了无法解析的工作流状态');
      }
    };
    source.addEventListener('workflow', update as EventListener);
    return () => source.close();
  }, [trackedRunId]);

  useEffect(() => {
    if (!waitingPlanRevision || !workflow?.plan) return;
    if (
      workflow.run.run_id === waitingPlanRevision.runId
      && workflow.plan.version > waitingPlanRevision.baseVersion
    ) {
      setWaitingPlanRevision(null);
      setPlanNotice(`Plan 已更新为 Revision ${workflow.plan.version}`);
      planScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [waitingPlanRevision, workflow]);

  const handleProcessStatus = useCallback((status: TerminalProcessStatus) => {
    setProcess(status);
    if (status.active_run_id) {
      trackedRunIdRef.current = status.active_run_id;
      setTrackedRunId(status.active_run_id);
    }
  }, []);

  const handleTerminalError = useCallback((message: string) => {
    setError(message);
  }, []);

  const startTerminal = async (mode: 'new' | 'resume' | 'fresh' = 'new') => {
    setBusy(true);
    setError(null);
    try {
      const normalizedProjectRoot = projectRoot.trim();
      if (!normalizedProjectRoot) {
        throw new Error('项目目录为空；请使用后端默认路径或输入一个存在的目录。');
      }
      const request: Record<string, unknown> = {
        project_root: normalizedProjectRoot,
        claude_command: claudeCommand.trim() || 'claude',
        rows: 36,
        cols: 120,
      };
      if (mode === 'resume' && process) {
        request.resume_claude_session_id = process.claude_session_id;
      }
      if (mode === 'resume' && !process && recoveryClaudeSessionId) {
        request.resume_claude_session_id = recoveryClaudeSessionId;
      }
      if (mode === 'fresh' && trackedRunId) {
        request.fresh_run_id = trackedRunId;
      }
      const body = await responseJson(await fetch('/api/terminal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      }));
      setProcess(body.session);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const closeTerminal = async () => {
    if (!process) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/terminal/${process.session_id}`, {
        method: 'DELETE',
      }));
      setProcess(body.session);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const startRecording = async () => {
    if (!initialTask.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: initialTask.trim(),
          input_files: initialInputFiles.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
          checkpoint_mode: 'plan',
        }),
      }));
      trackedRunIdRef.current = body.state.run.run_id;
      setWorkflow(body.state);
      setTrackedRunId(body.state.run.run_id);
      resetPlanModule();
      setInitialTask('');
      setInitialInputFiles('');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const approvePlan = async () => {
    if (!workflow) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/approve-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: '用户通过 AgentVAST Web 确认当前 Plan' }),
      }));
      setWorkflow(body.state);
      setEditingPlan(false);
      setPlanNotice(`Revision ${body.state.plan?.version ?? ''} 已确认，Claude 将继续执行。`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const beginPlanEdit = () => {
    if (!workflow?.plan) return;
    setPlanDraft(workflow.plan.nodes.map((node) => ({
      ...node,
      depends_on: [...node.depends_on],
      required_artifacts: [...node.required_artifacts],
    })));
    setPlanChangeReason('');
    setEditingPlan(true);
  };

  const updatePlanNode = (nodeId: string, update: Partial<PlanNode>) => {
    setPlanDraft((current) => current.map((node) => (
      node.node_id === nodeId ? { ...node, ...update } : node
    )));
  };

  const insertPlanNode = (targetId: string, position: 'before' | 'after') => {
    setPlanDraft((current) => {
      const targetIndex = current.findIndex((node) => node.node_id === targetId);
      if (targetIndex < 0) return current;
      const target = current[targetIndex];
      if (position === 'before' && target.status !== 'pending') return current;
      const newId = `new-node-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
      const inserted: PlanNode = {
        node_id: newId,
        objective: '',
        depends_on: position === 'before' ? [...target.depends_on] : [targetId],
        required_artifacts: ['code'],
        status: 'pending',
      };
      const revised = current.map((node) => {
        if (position === 'before' && node.node_id === targetId) {
          return { ...node, depends_on: [newId] };
        }
        if (
          position === 'after'
          && node.node_id !== targetId
          && node.status === 'pending'
          && node.depends_on.includes(targetId)
        ) {
          return {
            ...node,
            depends_on: node.depends_on.map((value) => (
              value === targetId ? newId : value
            )),
          };
        }
        return node;
      });
      revised.splice(position === 'before' ? targetIndex : targetIndex + 1, 0, inserted);
      return revised;
    });
  };

  const removePlanNode = (nodeId: string) => {
    setPlanDraft((current) => {
      const removed = current.find((node) => node.node_id === nodeId);
      if (!removed || removed.status !== 'pending') return current;
      return current
        .filter((node) => node.node_id !== nodeId)
        .map((node) => ({
          ...node,
          depends_on: Array.from(new Set(node.depends_on.flatMap((value) => (
            value === nodeId ? removed.depends_on : [value]
          )))),
        }));
    });
  };

  const requestPlanRevision = async () => {
    if (!workflow?.plan || !planRevisionRequest.trim()) return;
    const submittedPlanVersion = workflow.plan.version;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/interventions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_type: 'planning_input',
          content: planRevisionRequest.trim(),
        }),
      }));
      setWorkflow(body.state);
      setWaitingPlanRevision({
        runId: workflow.run.run_id,
        baseVersion: submittedPlanVersion,
      });
      setPlanNotice(`已要求 Claude 重新规划，等待 Revision ${submittedPlanVersion + 1}…`);
      setPlanRevisionRequest('');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const savePlan = async () => {
    if (!workflow?.plan) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/plan`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          change_reason: planChangeReason.trim() || '用户在 AgentVAST Web 修改了后续 Plan',
          nodes: planDraft.map((node) => ({
            node_id: node.node_id,
            objective: node.objective.trim(),
            depends_on: node.depends_on,
            required_artifacts: node.required_artifacts,
          })),
        }),
      }));
      setWorkflow(body.state);
      setEditingPlan(false);
      setPlanChangeReason('');
      setPlanNotice(`Revision ${body.state.plan.version} 已保存，尚未执行；请确认当前版本。`);
      planScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const startNewTaskTrace = async () => {
    if (!workflow || !newTraceTask.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/new-task-trace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: newTraceTask.trim(),
          input_files: newTraceInputFiles.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
          checkpoint_mode: 'plan',
        }),
      }));
      trackedRunIdRef.current = body.state.run.run_id;
      setWorkflow(body.state);
      setTrackedRunId(body.state.run.run_id);
      resetPlanModule();
      resetComposer();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const submitIntervention = async () => {
    if (!workflow || !intervention.trim()) return;
    const submittedRunId = workflow.run.run_id;
    const submittedPlanVersion = workflow.plan?.version ?? 0;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/interventions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_type: interventionType,
          content: intervention.trim(),
        }),
      }));
      setWorkflow(body.state);
      if (interventionType === 'planning_input') {
        setWaitingPlanRevision({
          runId: submittedRunId,
          baseVersion: submittedPlanVersion,
        });
        setPlanNotice(`已提交追加分析，等待 Claude 创建 Revision ${submittedPlanVersion + 1}…`);
      } else {
        setPlanNotice('输入已提交给当前 Trace，等待 Claude 处理。');
      }
      setIntervention('');
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const abortRecording = async () => {
    if (!workflow) return;
    if (!window.confirm('确认放弃并中止当前 Trace？未完成的 Node 会保留为中断状态。')) return;
    setBusy(true);
    setError(null);
    try {
      const body = await responseJson(await fetch(`/api/runs/${workflow.run.run_id}/abort`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户通过 AgentVAST Web 中止记录' }),
      }));
      setWorkflow(body.state);
      trackedRunIdRef.current = null;
      setTrackedRunId(null);
      resetPlanModule();
      resetComposer();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const finishTrace = async () => {
    if (!workflow) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/runs/${workflow.run.run_id}/finish`, {
        method: 'POST',
      });
      if (response.status === 404) {
        throw new Error('当前后端版本不支持完成 Trace，请重新运行“启动AgentVAST.bat”后再试');
      }
      const body = await responseJson(response);
      setWorkflow(body.state);
      trackedRunIdRef.current = null;
      setTrackedRunId(null);
      resetPlanModule();
      resetComposer();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const running = process?.state === 'running';
  const runActive = workflow?.run.status === 'active';
  const activeNode = useMemo(
    () => workflow?.nodes.find((node) => node.status === 'active') ?? null,
    [workflow],
  );
  const workflowPhase = workflow?.run.phase ?? (
    !runActive
      ? workflow?.run.status
      : workflow?.run.awaiting_user && workflow.run.checkpoint_kind === 'plan'
      ? 'plan_review'
      : !workflow?.plan
      ? 'planning'
      : activeNode
      ? 'executing'
      : workflow.pending_user_inputs.length > 0
      ? 'handling_input'
      : workflow.plan.nodes.every((node) => node.status === 'completed')
      ? 'idle'
      : 'ready'
  );
  const waitingForPlan = workflowPhase === 'plan_review';
  const currentPlanComplete = workflowPhase === 'idle';
  const hasPendingInput = Boolean(workflow?.pending_user_inputs.length);
  const planDraftChanged = Boolean(workflow?.plan && JSON.stringify(
    planDraft.map(({ node_id, objective, depends_on, required_artifacts }) => ({
      node_id,
      objective: objective.trim(),
      depends_on,
      required_artifacts,
    })),
  ) !== JSON.stringify(
    workflow.plan.nodes.map(({ node_id, objective, depends_on, required_artifacts }) => ({
      node_id,
      objective: objective.trim(),
      depends_on,
      required_artifacts,
    })),
  ));
  const canStartNewTrace = Boolean(
    workflowPhase === 'idle'
    && !activeNode
    && !hasPendingInput,
  );
  const traceInputLocked = Boolean(
    workflowPhase === 'planning'
    || workflowPhase === 'plan_review'
    || workflowPhase === 'handling_input'
    || waitingPlanRevision,
  );

  useEffect(() => {
    if (newTraceOpen && !canStartNewTrace) {
      setNewTraceOpen(false);
      setNewTraceTask('');
      setNewTraceInputFiles('');
    }
  }, [canStartNewTrace, newTraceOpen]);

  const phaseLabel: Record<string, string> = {
    planning: '生成计划',
    plan_review: '等待确认计划',
    node_review: '等待确认节点',
    checkpoint: '等待人工确认',
    ready: '准备执行',
    executing: activeNode?.node_id ?? '执行中',
    handling_input: '处理用户输入',
    idle: '等待后续分析',
    completed: '已完成',
    aborted: '已中止',
    failed: '失败',
  };

  return (
    <div className="h-full min-h-0 p-4 grid grid-cols-[minmax(640px,1fr)_390px] gap-4">
      <section className="min-h-0 flex flex-col rounded-3xl border border-[rgba(184,165,143,0.48)] bg-[rgba(255,255,255,0.86)] shadow-lg p-3">
        <div className="h-11 shrink-0 flex items-center px-2 gap-3">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#d96c55]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#dcaa55]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#719d63]" />
          </div>
          <span className="font-mono text-xs text-muted">Claude Code · interactive ConPTY</span>
          {runActive && (
            <span className="px-2.5 py-1 rounded-full text-[10px] font-mono text-accent bg-[#fff0e6] border border-[#e7b08d]">
              RECORDING · {phaseLabel[workflowPhase ?? 'planning'] ?? workflowPhase}
            </span>
          )}
          <span className={`ml-auto px-2.5 py-1 rounded-full text-[10px] font-mono border ${
            running && socketState === 'connected'
              ? 'text-green-700 bg-green-50 border-green-200'
              : 'text-muted bg-white border-line'
          }`}>
            {running ? 'PROCESS RUNNING' : 'NO ACTIVE PROCESS'} · WS {socketState.toUpperCase()}
          </span>
        </div>
        <div className="flex-1 min-h-0">
          <ClaudeTerminal
            ref={terminalRef}
            sessionId={process?.session_id ?? null}
            onSocketState={setSocketState}
            onProcessStatus={handleProcessStatus}
            onError={handleTerminalError}
          />
        </div>
      </section>

      <aside className="min-h-0 overflow-hidden flex flex-col rounded-3xl border border-[rgba(184,165,143,0.48)] bg-panel shadow-lg p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-serif text-xl">Claude 与记录控制</h2>
            <p className="text-xs text-muted mt-1 leading-5">普通对话和 AgentVAST 记录共用同一个 Claude 会话。</p>
          </div>
          <span className={`mt-1 w-2.5 h-2.5 rounded-full ${backendState === 'online' ? 'bg-green-500' : backendState === 'checking' ? 'bg-amber-400' : 'bg-red-500'}`} />
        </div>

        <div ref={planScrollRef} className="flex-1 min-h-0 overflow-auto pr-1">

        {!running && (
          <div className="mt-5 space-y-3">
            <label className="block">
              <span className="flex items-center justify-between gap-2 text-[10px] font-mono text-muted mb-1">
                <span>PROJECT DIRECTORY</span>
                <button
                  type="button"
                  disabled={!defaultProjectRoot}
                  onClick={() => {
                    projectRootEditedRef.current = false;
                    setProjectRoot(defaultProjectRoot);
                  }}
                  className="text-accent disabled:opacity-40"
                >
                  使用后端默认路径
                </button>
              </span>
              <input
                value={projectRoot}
                onChange={(event) => {
                  projectRootEditedRef.current = true;
                  setProjectRoot(event.target.value);
                }}
                placeholder={defaultProjectRoot || 'C:\\path\\to\\analysis-project'}
                className="w-full px-3 py-2 rounded-xl border border-line bg-white text-xs font-mono outline-none focus:border-accent"
              />
            </label>
            <label className="block">
              <span className="block text-[10px] font-mono text-muted mb-1">CLAUDE COMMAND</span>
              <input value={claudeCommand} onChange={(event) => setClaudeCommand(event.target.value)} className="w-full px-3 py-2 rounded-xl border border-line bg-white text-xs font-mono outline-none focus:border-accent" />
            </label>
            <div className="p-2.5 rounded-xl border border-line bg-white text-xs">
              Claude 统一以完全权限模式启动
              <span className="block text-muted mt-1">跳过工具授权提问</span>
            </div>
            {process || recoveryClaudeSessionId ? (
              <div className="grid grid-cols-2 gap-2">
                <button disabled={busy} onClick={() => void startTerminal('resume')} className="px-3 py-2.5 rounded-xl bg-accent text-white text-xs disabled:opacity-40">恢复原会话</button>
                {runActive && trackedRunId ? (
                  <button disabled={busy} onClick={() => void startTerminal('fresh')} className="px-3 py-2.5 rounded-xl border border-accent text-accent bg-white text-xs disabled:opacity-40">新会话继续 Run</button>
                ) : (
                  <button disabled={busy} onClick={() => void startTerminal('new')} className="px-3 py-2.5 rounded-xl border border-accent text-accent bg-white text-xs disabled:opacity-40">启动新会话</button>
                )}
              </div>
            ) : (
              <button disabled={busy || backendState !== 'online'} onClick={() => void startTerminal()} className="w-full px-4 py-3 rounded-xl bg-accent text-white text-sm font-semibold shadow-md disabled:opacity-45">
                {busy ? '处理中…' : '启动 Claude'}
              </button>
            )}
          </div>
        )}

        {workflow && (
          <section className="mt-5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-muted">AGENTVAST RUN</span>
              <span className={`px-2 py-1 rounded-full text-[10px] font-mono ${runActive ? 'text-green-700 bg-green-50' : 'text-muted bg-[#f2eee9]'}`}>{workflow.run.status.toUpperCase()}</span>
            </div>
            <div className="mt-2 text-xs font-mono break-all">{workflow.run.run_id}</div>
            <div className="mt-2 text-sm leading-5">{workflow.run.task_description}</div>

            {planNotice && (
              <div className={`mt-3 px-3 py-2 rounded-xl border text-xs leading-5 ${waitingPlanRevision ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-green-200 bg-green-50 text-green-800'}`}>
                {planNotice}
              </div>
            )}

            {workflow.plan ? (
              <div className="mt-4">
                <div className="flex items-center justify-between text-[10px] font-mono text-muted">
                  <span>PLAN REVISION {workflow.plan.version}</span>
                  <div className="flex items-center gap-2">
                    <span>{workflow.plan.trigger}</span>
                    <button disabled={busy} onClick={() => void refresh()} className="px-2 py-1 rounded-lg border border-line bg-white text-muted font-sans disabled:opacity-40">刷新</button>
                    {runActive && !editingPlan && (
                      <button disabled={busy || hasPendingInput} onClick={beginPlanEdit} className="px-2 py-1 rounded-lg border border-line bg-white text-accent font-sans disabled:opacity-40">编辑 Plan</button>
                    )}
                  </div>
                </div>
                <div className="mt-2 space-y-2">
                  {(editingPlan ? planDraft : workflow.plan.nodes).map((node) => (
                    <div key={node.node_id} className={`p-2.5 rounded-xl border ${node.status === 'active' ? 'border-accent bg-[#fff6ef]' : node.status === 'completed' ? 'border-green-200 bg-green-50' : 'border-line bg-white'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-mono text-accent">{node.node_id}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-[9px] font-mono text-muted">{node.status.toUpperCase()}</span>
                          {editingPlan && node.status === 'pending' && (
                            <button onClick={() => removePlanNode(node.node_id)} className="text-[10px] text-red-600">删除</button>
                          )}
                        </div>
                      </div>
                      {editingPlan ? (
                        <div className="mt-2 space-y-2">
                          <textarea
                            value={node.objective}
                            disabled={node.status !== 'pending'}
                            onChange={(event) => updatePlanNode(node.node_id, { objective: event.target.value })}
                            rows={2}
                            placeholder="Node 的语义分析目标"
                            className="w-full px-2.5 py-2 rounded-lg border border-line bg-white text-xs leading-4 outline-none disabled:bg-[#f2eee9] disabled:text-muted resize-none"
                          />
                          <label className="block">
                            <span className="block text-[9px] font-mono text-muted mb-1">依赖 Node ID（逗号分隔）</span>
                            <input
                              value={node.depends_on.join(', ')}
                              disabled={node.status !== 'pending'}
                              onChange={(event) => updatePlanNode(node.node_id, {
                                depends_on: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                              })}
                              className="w-full px-2.5 py-1.5 rounded-lg border border-line bg-white text-[10px] font-mono outline-none disabled:bg-[#f2eee9] disabled:text-muted"
                            />
                          </label>
                          <label className="block">
                            <span className="block text-[9px] font-mono text-muted mb-1">产物类型（code, data, report, visualization）</span>
                            <input
                              value={node.required_artifacts.join(', ')}
                              disabled={node.status !== 'pending'}
                              onChange={(event) => updatePlanNode(node.node_id, {
                                required_artifacts: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                              })}
                              className="w-full px-2.5 py-1.5 rounded-lg border border-line bg-white text-[10px] font-mono outline-none disabled:bg-[#f2eee9] disabled:text-muted"
                            />
                          </label>
                          {node.status !== 'pending' && <p className="text-[10px] text-muted">该 Node 已开始，计划定义只读；它的产物仍可供后续 Node 读取和修改。</p>}
                          <div className="grid grid-cols-2 gap-2">
                            <button disabled={node.status !== 'pending'} onClick={() => insertPlanNode(node.node_id, 'before')} className="px-2 py-1.5 rounded-lg border border-dashed border-line bg-white text-[10px] text-accent disabled:opacity-35">+ 在此前插入</button>
                            <button onClick={() => insertPlanNode(node.node_id, 'after')} className="px-2 py-1.5 rounded-lg border border-dashed border-line bg-white text-[10px] text-accent">+ 在此后插入</button>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-1">
                          <p className="text-xs leading-4">{node.objective}</p>
                          <div className="mt-1.5 space-y-1 text-[9px] font-mono text-muted">
                            <div>依赖：{node.depends_on.length ? node.depends_on.join(', ') : '无'}</div>
                            <div>产物：{node.required_artifacts.join(', ')}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {editingPlan && (
                  <div className="mt-3 p-3 rounded-xl border border-line bg-[#fffaf6]">
                    <p className="mb-2 text-[10px] text-muted leading-4">保存只更新结构化 Plan，不会向 Claude 提交执行；保存后仍需确认当前 Revision。</p>
                    <textarea value={planChangeReason} onChange={(event) => setPlanChangeReason(event.target.value)} rows={2} placeholder="修改原因（可选，留空时使用默认说明）" className="w-full mt-2 px-3 py-2 rounded-lg border border-line bg-white text-xs leading-4 outline-none resize-none" />
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <button disabled={busy} onClick={() => setEditingPlan(false)} className="px-3 py-2 rounded-lg border border-line bg-white text-xs disabled:opacity-40">取消</button>
                      <button disabled={busy || planDraft.length === 0 || !planDraftChanged} onClick={() => void savePlan()} className="px-3 py-2 rounded-lg bg-accent text-white text-xs disabled:opacity-40">仅保存 Revision</button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-3 p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800">Claude 正在生成初始 Plan。实质分析工具已被门禁阻止。</div>
            )}

            {waitingForPlan && (
              <div className="mt-3 p-3 rounded-xl border border-accent bg-[#fff6ef]">
                <div className="text-sm font-semibold">等待你确认 Revision {workflow.plan?.version}</div>
                <p className="mt-1 text-xs text-muted leading-5">可以手动编辑，也可以用自然语言要求 Claude 重新生成一版；确认当前版本后才会执行。</p>
                <textarea value={planRevisionRequest} onChange={(event) => setPlanRevisionRequest(event.target.value)} rows={3} placeholder="例如：当前计划过于宽泛，请先验证数据字段，再拆分为清洗、统计和结论三个节点。" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-xs leading-5 outline-none resize-none" />
                <button disabled={busy || editingPlan || !planRevisionRequest.trim() || Boolean(waitingPlanRevision)} onClick={() => void requestPlanRevision()} className="w-full mt-2 px-3 py-2 rounded-xl border border-accent bg-white text-accent text-xs disabled:opacity-40">要求 Claude 重新规划</button>
                <button disabled={busy || editingPlan} onClick={() => void approvePlan()} className="w-full mt-2 px-3 py-2.5 rounded-xl bg-accent text-white text-sm disabled:opacity-40">确认当前 Revision 并执行</button>
              </div>
            )}

            {runActive && currentPlanComplete && !newTraceOpen && (
              <div className="mt-3 p-3 rounded-xl border border-green-200 bg-green-50">
                <div className="text-sm font-semibold text-green-800">当前 Plan 已完成，Trace 保持开启</div>
                <p className="mt-1 text-xs text-green-700 leading-5">在右下输入后续分析要求，会基于当前 Run、现有 Plan 和产物追加新的 Plan Revision，不会重新开始。</p>
                {!running && (
                  <button disabled={busy} onClick={() => void finishTrace()} className="w-full mt-2 px-3 py-2 rounded-xl border border-green-300 bg-white text-green-700 text-xs disabled:opacity-40">完成并保存 Trace</button>
                )}
              </div>
            )}

          </section>
        )}

        {error && <div className="mt-4 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-xs leading-5 break-words">{error}</div>}

        </div>

        {running && (
          <div className="shrink-0 mt-3 pt-3 border-t border-line">
            {!runActive ? (
              <div className="p-3 rounded-2xl border border-[rgba(217,119,69,0.25)] bg-[#fffaf6]">
                <div className="text-[10px] font-mono text-accent">当前没有活动 Trace</div>
                <textarea value={initialTask} onChange={(event) => setInitialTask(event.target.value)} rows={3} placeholder="输入新的数据分析任务" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-xs leading-5 outline-none focus:border-accent resize-none" />
                <textarea value={initialInputFiles} onChange={(event) => setInitialInputFiles(event.target.value)} rows={2} placeholder="输入文件可留空，由 Claude 自动判断；多个文件每行一个" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-[10px] font-mono leading-4 outline-none focus:border-accent resize-none" />
                <button disabled={busy || !initialTask.trim()} onClick={() => void startRecording()} className="w-full mt-2 px-4 py-2.5 rounded-xl bg-accent text-white text-sm font-semibold disabled:opacity-45">创建并开始 Trace</button>
              </div>
            ) : workflowPhase === 'planning' ? (
              <div className="p-3 rounded-2xl border border-amber-200 bg-amber-50">
                <div className="text-xs font-semibold text-amber-800">Claude 正在生成当前 Trace 的 Plan</div>
                <p className="mt-1 text-[10px] text-amber-700 leading-4">任务已经提交，请等待 Plan 出现在右上方，不要再次提交任务。</p>
              </div>
            ) : waitingForPlan ? (
              <div className="p-3 rounded-2xl border border-accent bg-[#fff6ef]">
                <div className="text-xs font-semibold text-accent">当前任务正在等待 Plan 确认</div>
                <p className="mt-1 text-[10px] text-muted leading-4">请在右上方手动编辑、自然语言要求重新规划，或确认当前 Plan。确认前不会执行分析。</p>
              </div>
            ) : newTraceOpen ? (
              <div className="p-3 rounded-2xl border border-slate-300 bg-slate-50">
                <div className="text-[10px] font-mono text-slate-700">NEW TASK TRACE</div>
                <p className="mt-1 text-[10px] text-muted leading-4">保存并导出当前 Run，然后在同一 Claude 会话创建新 Run。</p>
                <textarea value={newTraceTask} onChange={(event) => setNewTraceTask(event.target.value)} rows={3} placeholder="输入新的独立数据分析任务" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-xs leading-5 outline-none resize-none" />
                <textarea value={newTraceInputFiles} onChange={(event) => setNewTraceInputFiles(event.target.value)} rows={2} placeholder="输入文件可留空，由 Claude 自动判断" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-[10px] font-mono leading-4 outline-none resize-none" />
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <button disabled={busy} onClick={() => resetComposer()} className="px-3 py-2 rounded-xl border border-line bg-white text-xs disabled:opacity-40">取消</button>
                  <button disabled={busy || !newTraceTask.trim()} onClick={() => void startNewTaskTrace()} className="px-3 py-2 rounded-xl bg-slate-800 text-white text-xs disabled:opacity-40">保存当前并创建新 Trace</button>
                </div>
              </div>
            ) : (
              <div className="p-3 rounded-2xl border border-line bg-[#fffaf6]">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-mono text-accent">{currentPlanComplete ? '继续当前 Trace' : '介入当前 Trace'}</span>
                  <button disabled={busy || !canStartNewTrace} onClick={() => setNewTraceOpen(true)} className="px-2 py-1 rounded-lg border border-slate-300 bg-white text-[10px] text-slate-700 disabled:opacity-40">New Task Trace</button>
                </div>
                <select disabled={traceInputLocked} value={interventionType} onChange={(event) => setInterventionType(event.target.value as InterventionType)} className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-xs outline-none disabled:bg-[#f2eee9]">
                  <option value="planning_input">追加分析或调整后续计划</option>
                  <option value="challenge">对分析提出异议</option>
                  <option value="analysis_guidance">提供分析指导</option>
                </select>
                <textarea disabled={traceInputLocked} value={intervention} onChange={(event) => setIntervention(event.target.value)} rows={3} placeholder="输入后续分析要求、计划调整、异议或指导" className="w-full mt-2 px-3 py-2 rounded-xl border border-line bg-white text-xs leading-5 outline-none resize-none disabled:bg-[#f2eee9]" />
                <button disabled={busy || traceInputLocked || !intervention.trim()} onClick={() => void submitIntervention()} className="w-full mt-2 px-3 py-2.5 rounded-xl bg-accent text-white text-xs disabled:opacity-40">提交到当前 Trace</button>
                {traceInputLocked && <p className="mt-1 text-[9px] leading-4 text-amber-700">上一条输入或 Plan 正在处理，请等待状态更新后再提交。</p>}
                <p className="mt-1 text-[9px] leading-4 text-muted">Claude 执行中时内容会排队；需要立即改变执行，请先发送 Ctrl+C。</p>
              </div>
            )}

            <div className="mt-2 grid grid-cols-3 gap-2">
              <button onClick={() => terminalRef.current?.interrupt()} className="px-2 py-2 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 text-[10px]">Ctrl+C</button>
              {currentPlanComplete ? (
                <button disabled={busy} onClick={() => void finishTrace()} className="px-2 py-2 rounded-xl border border-green-200 bg-green-50 text-green-700 text-[10px] disabled:opacity-40">完成并保存 Trace</button>
              ) : runActive ? (
                <button disabled={busy} onClick={() => void abortRecording()} className="px-2 py-2 rounded-xl border border-red-200 bg-red-50 text-red-700 text-[10px] disabled:opacity-40">放弃并中止 Trace</button>
              ) : <span />}
              <button disabled={busy} onClick={() => void closeTerminal()} className="px-2 py-2 rounded-xl border border-red-200 bg-white text-red-700 text-[10px] disabled:opacity-40">关闭 Claude</button>
            </div>
          </div>
        )}

        {!running && (
          <div className="shrink-0 mt-3 pt-3 border-t border-line space-y-1 text-[10px] font-mono">
            <div className="flex justify-between"><span className="text-muted">SERVICE</span><span>{backendState.toUpperCase()}</span></div>
            <div className="flex justify-between"><span className="text-muted">PROCESS</span><span>{process?.state.toUpperCase() ?? 'NONE'}</span></div>
          </div>
        )}
      </aside>
    </div>
  );
}

export default ClaudeTerminalPage;
