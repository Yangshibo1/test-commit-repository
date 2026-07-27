import { useState, useEffect } from 'react';

interface FollowPanelProps {
  isOpen: boolean;
  onClose: () => void;
  selectedContext?: {
    opentrace_session?: string;
    selected_step?: {
      id: string;
      name: string;
      input_files: string[];
      output_files: string[];
      code_files: string[];
    };
    selected_node?: {
      id: string;
      type: string;
      location?: string;
      name?: string;
      description?: string;
    };
    analysis_artifact?: unknown;
  };
  DEFAULT_WORKSPACE?: string;
}

export default function FollowPanel({ isOpen, onClose, selectedContext, DEFAULT_WORKSPACE = 'C:\\Users\\83734\\Desktop\\opentrace\\test-commit-repository' }: FollowPanelProps) {
  const [question, setQuestion] = useState('');
  const [workspace, setWorkspace] = useState(DEFAULT_WORKSPACE);
  const [sessionId, setSessionId] = useState('');
  const [commandPreview, setCommandPreview] = useState('');
  const [copyStatus, setCopyStatus] = useState('');

  useEffect(() => {
    updateCommandPreview();
  }, [question, workspace, sessionId, selectedContext]);

  const updateCommandPreview = () => {
    const context = selectedContext ? JSON.stringify(selectedContext, null, 2) : '{}';
    const prompt = `${question}\n\nCurrent frontend selection context (please incorporate if relevant):\n${context}`.trim();

    const resumePart = sessionId ? ` --resume "${sessionId}"` : '';
    const workspaceQuoted = `"${workspace.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
    const promptQuoted = `"${prompt.replace(/"/g, '\\"')}"`;

    setCommandPreview(`cd ${workspaceQuoted} && claude -p ${promptQuoted}${resumePart}`);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(commandPreview);
      setCopyStatus('Copied');
      setTimeout(() => setCopyStatus(''), 2000);
    } catch {
      setCopyStatus('Copy failed');
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed right-4 top-28 w-[560px] max-w-[calc(100vw-2rem)] max-h-[calc(100vh-8rem)] z-20 overflow-auto rounded-3xl border border-[rgba(184,165,143,0.58)] bg-[rgba(255,255,255,0.97)] shadow-[0_24px_80px_rgba(91,64,42,0.18)] p-4 backdrop-blur-xl"
    >
      <h3 className="font-serif text-xl mb-2">Ask Claude follow-up</h3>
      <p className="text-muted text-xs leading-relaxed mb-4">
        Fill in the question, workspace, and historical Claude session id. The page will generate a copyable command for continuing the task with inherited history.
      </p>

      <div className="grid gap-2.5">
        <div>
          <label className="block text-accent font-mono text-xs uppercase tracking-widest mb-1">
            Question
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Enter your question or task..."
            className="w-full border border-[rgba(184,165,143,0.48)] rounded-xl p-2.5 text-ink bg-[rgba(255,250,245,0.76)] font-mono text-xs outline-none resize-y min-h-28 leading-relaxed"
          />
        </div>
        <div>
          <label className="block text-accent font-mono text-xs uppercase tracking-widest mb-1">
            Workspace
          </label>
          <input
            type="text"
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            placeholder="e.g., C:\\Users\\83734\\Desktop\\opentrace\\test-commit-repository"
            className="w-full border border-[rgba(184,165,143,0.48)] rounded-xl p-2.5 text-ink bg-[rgba(255,250,245,0.76)] font-mono text-xs outline-none"
          />
        </div>
        <div>
          <label className="block text-accent font-mono text-xs uppercase tracking-widest mb-1">
            Inherited Claude session id
          </label>
          <input
            type="text"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="e.g., 31671665-2cb5-4def-ab0a-dc0060d0c065"
            className="w-full border border-[rgba(184,165,143,0.48)] rounded-xl p-2.5 text-ink bg-[rgba(255,250,245,0.76)] font-mono text-xs outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center mt-1">
          <button
            onClick={updateCommandPreview}
            className="px-3 py-2 rounded-full border border-[rgba(184,165,143,0.58)] text-ink bg-[rgba(255,255,255,0.9)] font-mono text-xs cursor-pointer hover:border-accent transition-colors"
          >
            Build command
          </button>
          <button
            onClick={handleCopy}
            className="px-3 py-2 rounded-full border border-[rgba(184,165,143,0.58)] text-ink bg-[rgba(255,255,255,0.9)] font-mono text-xs cursor-pointer hover:border-accent transition-colors"
          >
            Copy command
          </button>
          <button
            onClick={onClose}
            className="px-3 py-2 rounded-full border border-[rgba(184,165,143,0.58)] text-ink bg-[rgba(255,255,255,0.9)] font-mono text-xs cursor-pointer hover:border-accent transition-colors"
          >
            Close
          </button>
          <span className="text-green-600 font-mono text-xs">{copyStatus}</span>
        </div>
      </div>

      <div className="mt-3">
        <pre className="bg-[rgba(255,255,255,0.72)] border border-[rgba(184,165,143,0.42)] rounded-xl p-3 max-h-44 overflow-auto text-[#34444e] font-mono text-xs">
          {commandPreview || 'Fill in to generate claude -p --resume command.'}
        </pre>
      </div>
    </div>
  );
}
