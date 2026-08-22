import { useState } from 'react';
import RecordPage from './App';
import ClaudeTerminalPage from './pages/ClaudeTerminalPage';

type Page = 'claude' | 'records';

function Workbench() {
  const [page, setPage] = useState<Page>('claude');

  return (
    <div className="h-screen flex flex-col overflow-hidden text-ink">
      <header className="h-16 shrink-0 flex items-center gap-6 px-6 border-b border-[rgba(184,165,143,0.55)] bg-[rgba(255,250,240,0.9)] backdrop-blur-2xl z-20">
        <div className="flex items-center gap-3 min-w-[246px]">
          <div className="w-10 h-10 border border-[rgba(217,119,69,0.42)] rounded-xl flex items-center justify-center bg-gradient-to-br from-white to-[#fff6ef] shadow-md">
            <span className="text-accent font-bold text-sm rotate-[-4deg]">AV</span>
          </div>
          <div>
            <div className="font-serif text-lg leading-none">AgentVAST</div>
            <div className="text-[10px] text-muted font-mono mt-1">LOCAL CLAUDE WORKBENCH</div>
          </div>
        </div>

        <nav className="flex items-center gap-1 p-1 rounded-xl bg-[rgba(234,223,212,0.55)] border border-[rgba(184,165,143,0.32)]">
          <button
            type="button"
            onClick={() => setPage('claude')}
            className={`px-5 py-2 rounded-lg text-sm transition-all ${
              page === 'claude'
                ? 'bg-white text-accent shadow-sm font-semibold'
                : 'text-muted hover:text-ink'
            }`}
          >
            Claude 对话
          </button>
          <button
            type="button"
            onClick={() => setPage('records')}
            className={`px-5 py-2 rounded-lg text-sm transition-all ${
              page === 'records'
                ? 'bg-white text-accent shadow-sm font-semibold'
                : 'text-muted hover:text-ink'
            }`}
          >
            工作流记录
          </button>
        </nav>

        <div className="ml-auto text-[11px] text-muted font-mono">
          P0 · CLI TERMINAL BRIDGE
        </div>
      </header>

      <main className="flex-1 min-h-0">
        {page === 'claude' ? <ClaudeTerminalPage /> : <RecordPage />}
      </main>
    </div>
  );
}

export default Workbench;
