import { useState } from 'react';
import ClaudeTerminalPage from './pages/ClaudeTerminalPage';
import ObserverPage from './pages/ObserverPage';
import { WorkbenchPage } from './types/navigation';

const pages: Array<[WorkbenchPage, string]> = [
  ['claude', 'Claude 运行'],
  ['transcript', '原始 Transcript'],
  ['workflow', '工作流可视化'],
  ['execution', 'Agent 详细执行工作流'],
];

function Workbench() {
  const [page, setPage] = useState<WorkbenchPage>('claude');
  const [observerOpened, setObserverOpened] = useState(false);
  const [requestedSessionId, setRequestedSessionId] = useState<string | null>(null);
  const [sessionRequestVersion, setSessionRequestVersion] = useState(0);

  const navigate = (nextPage: WorkbenchPage, sessionId?: string) => {
    if (sessionId) {
      setRequestedSessionId(sessionId);
      setSessionRequestVersion((version) => version + 1);
    }
    if (nextPage !== 'claude') setObserverOpened(true);
    setPage(nextPage);
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden text-ink">
      <header className="min-h-16 shrink-0 flex flex-wrap items-center gap-4 px-5 py-3 border-b border-line bg-[rgba(255,250,240,0.9)] backdrop-blur-2xl z-20">
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-10 h-10 border border-[rgba(217,119,69,0.42)] rounded-xl flex items-center justify-center bg-gradient-to-br from-white to-[#fff6ef] shadow-md">
            <span className="text-accent font-bold text-sm rotate-[-4deg]">AV</span>
          </div>
          <div>
            <div className="font-serif text-lg leading-none">AgentVAST</div>
            <div className="text-[10px] text-muted font-mono mt-1">LOCAL CLAUDE WORKBENCH</div>
          </div>
        </div>

        <nav aria-label="主导航" className="flex flex-wrap max-w-full items-center gap-1 p-1 rounded-xl bg-[rgba(234,223,212,0.55)] border border-line">
          {pages.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-current={page === value ? 'page' : undefined}
              onClick={() => navigate(value)}
              className={`px-4 py-2 rounded-lg text-sm whitespace-nowrap transition-all ${page === value ? 'bg-white text-accent shadow-sm font-semibold' : 'text-muted hover:text-ink'}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 min-h-0">
        <div className={page === 'claude' ? 'h-full' : 'hidden'}>
          <ClaudeTerminalPage onNavigate={navigate} visible={page === 'claude'} />
        </div>
        {observerOpened && (
          <div className={page === 'claude' ? 'hidden' : 'h-full'}>
            <ObserverPage
              view={page === 'transcript' ? 'raw' : page === 'execution' ? 'execution' : 'semantic'}
              onViewChange={(view) => navigate(view === 'raw' ? 'transcript' : view === 'execution' ? 'execution' : 'workflow')}
              requestedSessionId={requestedSessionId}
              sessionRequestVersion={sessionRequestVersion}
            />
          </div>
        )}
      </main>
    </div>
  );
}

export default Workbench;
