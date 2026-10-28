import { useEffect, useMemo, useState } from 'react';
import { ObserverMetrics } from '../types/observer';
import {
  buildTranscriptCards,
  buildTranscriptTools,
  contentBlocks,
  formatTranscript,
  parseTranscript,
  readableContent,
  TranscriptCard,
  TranscriptLine,
  TranscriptTool,
} from '../utils/transcript';

interface TranscriptViewProps {
  sessionId: string | null;
  focusLines: number[];
  turnCount?: number;
  refreshRevision?: number;
  onLocalMetricsChange: (metrics: ObserverMetrics | null) => void;
}

type TranscriptMode = 'chain' | 'raw' | 'tools';
const PAGE_SIZE = 40;
const tabs: Array<[TranscriptMode, string]> = [
  ['chain', '调用链视图'],
  ['raw', '原始日志'],
  ['tools', '工具详情'],
];
const accents = { system: '#0ea5e9', user: '#8b5cf6', assistant: '#16a34a', tool: '#d97745', result: '#0f766e', context: '#94a3b8' };

export default function TranscriptView({ sessionId, focusLines, turnCount, refreshRevision, onLocalMetricsChange }: TranscriptViewProps) {
  const [content, setContent] = useState('');
  const [source, setSource] = useState('');
  const [localFile, setLocalFile] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formatted, setFormatted] = useState(false);
  const [page, setPage] = useState(0);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [reload, setReload] = useState(0);
  const [view, setView] = useState<TranscriptMode>('chain');
  const [copied, setCopied] = useState(false);
  const lines = useMemo(() => parseTranscript(content), [content]);
  const cards = useMemo(() => buildTranscriptCards(lines), [lines]);
  const tools = useMemo(() => buildTranscriptTools(lines), [lines]);
  const displayedLog = useMemo(() => formatted ? formatTranscript(content) : content, [content, formatted]);
  const inferredTurns = useMemo(() => lines.filter((line) => line.type === 'user' && !contentBlocks(line).some((block) => block.type === 'tool_result')).length, [lines]);
  const rounds = !localFile && turnCount !== undefined ? turnCount : inferredTurns;
  useEffect(() => {
    onLocalMetricsChange(localFile ? {
      human_prompt_count: inferredTurns,
      tool_call_count: tools.filter((tool) => tool.requestLines.length).length,
      tool_error_count: tools.filter((tool) => tool.status === 'error').length,
      subagent_result_count: lines.filter((line) => line.type === 'subagent_result').length,
    } : null);
  }, [localFile, inferredTurns, tools, lines, onLocalMetricsChange]);
  const items = useMemo(() => view === 'chain'
    ? cards.map((card, index) => ({ index, lines: card.lines }))
    : tools.map((tool, index) => ({ index, lines: [...tool.requestLines, ...tool.resultLines] })), [cards, tools, view]);
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages - 1);
  const focusedLine = focusLines[0];
  const visibleItems = items.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  useEffect(() => {
    const controller = new AbortController();
    setContent('');
    setSource('');
    setError(null);
    setFormatted(false);
    setPage(0);
    setSelectedLine(null);
    setLocalFile(false);
    if (!sessionId) {
      setLoading(false);
      return () => controller.abort();
    }
    setLoading(true);
    void (async () => {
      try {
        const response = await fetch(`/api/observations/${encodeURIComponent(sessionId)}/transcript`, { signal: controller.signal });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `读取 Transcript 失败（HTTP ${response.status}）`);
        }
        const text = await response.text();
        if (controller.signal.aborted) return;
        setContent(text);
        setSource('transcript/transcript.jsonl');
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '读取 Transcript 失败');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [sessionId, reload]);

  useEffect(() => {
    if (!sessionId || !refreshRevision || localFile) return;
    const controller=new AbortController();
    void fetch(`/api/observations/${encodeURIComponent(sessionId)}/transcript`,{signal:controller.signal,cache:'no-store'})
      .then(async response=>{
        if (!response.ok) return;
        const text=await response.text();
        if (!controller.signal.aborted) {setContent(text);setSource('transcript/transcript.jsonl');setError(null);}
      }).catch(()=>{ /* Preserve content and scroll while live records are being published. */ });
    return ()=>controller.abort();
  },[sessionId,refreshRevision,localFile]);

  useEffect(() => {
    if (!focusedLine || localFile || !lines.length) return;
    setSelectedLine(focusedLine);
    setView('chain');
  }, [focusedLine, localFile, lines]);

  useEffect(() => {
    if (!selectedLine) return;
    const index = items.findIndex((item) => item.lines.includes(selectedLine));
    if (index >= 0) setPage(Math.floor(index / PAGE_SIZE));
  }, [selectedLine, view, items]);

  useEffect(() => {
    if (!selectedLine) return;
    const records = document.getElementById('transcript-panel')?.querySelectorAll<HTMLElement>('[data-source-lines]');
    Array.from(records || []).find((record) => record.dataset.sourceLines?.split(',').includes(String(selectedLine)))?.scrollIntoView({ block: 'nearest' });
  }, [selectedLine, currentPage, content, view]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    try {
      setContent(await file.text());
      setSource(file.name);
      setLocalFile(true);
      setFormatted(false);
      setPage(0);
      setSelectedLine(null);
      setError(null);
    } catch {
      setError('无法读取本地 Transcript 文件');
    }
  };

  const copyLog = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
    } catch {
      setError('复制失败，请在原始日志中选择内容后手动复制。');
    }
  };

  useEffect(() => { setCopied(false); }, [content]);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2200);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const switchView = (mode: TranscriptMode) => {
    setView(mode);
    setPage(0);
    setSelectedLine(null);
  };

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="shrink-0 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-2 border-b border-line bg-white">
        <div>
          <h2 className="text-base font-semibold">{view === 'chain' ? `调用链（共 ${rounds} 轮）` : view === 'tools' ? `工具详情（共 ${tools.length} 个调用）` : `原始日志（共 ${lines.length} 行）`}</h2>
          {view === 'raw' && <p className="text-[10px] text-muted font-mono" title={source}>{source || '选择会话或加载原始 JSONL 文件'}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" aria-label="Transcript 视图" className="flex items-center gap-1 rounded-xl bg-stone-100 p-1">
            {tabs.map(([mode, label]) => (
              <button key={mode} id={`transcript-tab-${mode}`} type="button" role="tab" aria-selected={view === mode} aria-controls="transcript-panel" onClick={() => switchView(mode)} className={`px-3 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${view === mode ? 'bg-white text-accent shadow-sm' : 'text-muted hover:text-ink'}`}>{label}</button>
            ))}
          </div>
          {view === 'raw' && <>
            <button type="button" disabled={loading || !content} aria-pressed={formatted} onClick={() => setFormatted(!formatted)} className="px-3 py-2 rounded-lg border border-line bg-white text-xs font-semibold whitespace-nowrap disabled:opacity-40">{formatted ? '还原原文' : '格式化'}</button>
            <label className="px-3 py-2 rounded-lg border border-line bg-white text-xs cursor-pointer whitespace-nowrap">
              加载 Transcript
              <input type="file" accept=".jsonl,.json,.txt" className="hidden" disabled={loading} onChange={(event) => void upload(event.target.files?.[0])} />
            </label>
          </>}
          <button type="button" aria-label="重新读取" title="重新读取" disabled={!sessionId || loading} onClick={() => setReload((value) => value + 1)} className="p-2 rounded-lg border border-line bg-white disabled:opacity-40">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 6.1A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.9" /></svg>
          </button>
          <button type="button" aria-label="复制日志" disabled={loading || !content} onClick={() => void copyLog()} className="flex items-center gap-2 px-3 py-2 rounded-xl border border-line bg-white text-xs font-semibold whitespace-nowrap disabled:opacity-40">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4" /></svg>
            <span role="status">{copied ? '已复制' : '复制日志'}</span>
          </button>
        </div>
      </div>
      {error && <div role="alert" className="mx-5 mt-3 p-3 rounded-xl border border-red-200 bg-red-50 text-red-700 text-xs">{error}</div>}
      <div id="transcript-panel" role="tabpanel" aria-labelledby={`transcript-tab-${view}`} className="flex-1 min-h-0 overflow-auto p-3 lg:p-4 space-y-3">
        {loading ? <p className="p-5 text-center text-sm text-muted">正在读取原始 Transcript…</p> : view === 'raw' ? (
          <pre aria-label="原始 Transcript 内容" className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-xs leading-5 font-mono">{displayedLog}</pre>
        ) : visibleItems.map((item) => (
          view === 'chain'
            ? <ChainCard key={cards[item.index].id} card={cards[item.index]} highlighted={item.lines.includes(selectedLine || -1)} lines={lines} />
            : <ToolCard key={tools[item.index].id} tool={tools[item.index]} sequence={item.index + 1} highlighted={item.lines.includes(selectedLine || -1)} />
        ))}
        {!loading && !error && (view === 'raw' ? !content : !items.length) && <p className="p-8 text-center text-sm text-muted">{view === 'tools' && lines.length ? '这份 Transcript 中没有工具调用记录。' : '尚无原始记录，请选择会话或加载 Transcript。'}</p>}
      </div>
      {view !== 'raw' && totalPages > 1 && <div className="shrink-0 flex items-center justify-between gap-2 px-4 py-2 border-t border-line bg-white text-xs">
        <span className="text-muted">{items.length} 条{view === 'tools' ? '工具记录' : '记录'} · {currentPage + 1} / {totalPages} 页</span>
        <div className="flex gap-2">
          <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} className="px-3 py-1 rounded-lg border border-line disabled:opacity-40">上一页</button>
          <button type="button" disabled={currentPage + 1 >= totalPages} onClick={() => setPage(currentPage + 1)} className="px-3 py-1 rounded-lg border border-line disabled:opacity-40">下一页</button>
        </div>
      </div>}
    </div>
  );
}

function CollapsibleText({ text, limit = 750 }: { text: string; limit?: number }) {
  const [expanded, setExpanded] = useState(false);
  const shortened = text.length > limit;
  return (
    <div className="rounded-lg bg-stone-50 px-3 py-2.5">
      <pre className="whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-[13px] leading-6 font-sans text-ink">{shortened && !expanded ? `${text.slice(0, limit)}…` : text}</pre>
      {shortened && <button type="button" onClick={() => setExpanded(!expanded)} className="mt-2 px-3 py-1 rounded-lg bg-stone-200/60 text-xs font-semibold text-stone-600">{expanded ? '收起' : '展开'}</button>}
    </div>
  );
}

function ChainCard({ card, highlighted, lines }: { card: TranscriptCard; highlighted: boolean; lines: TranscriptLine[] }) {
  return (
    <article id={`transcript-line-${card.lines[0]}`} data-source-lines={card.lines.join(',')} className={`rounded-xl border border-l-[4px] px-4 py-3.5 ${highlighted ? 'border-accent bg-orange-50/30 ring-1 ring-accent/20' : 'border-line bg-white'}`} style={{ borderLeftColor: accents[card.kind] }}>
      <div className="flex flex-wrap items-center gap-2 mb-2.5">
        <span className="inline-flex h-7 min-w-7 px-1.5 items-center justify-center rounded-md bg-sky-100 text-sky-700 text-sm font-semibold">{card.sequence}</span>
        <h3 className="text-sm font-semibold">{card.title}</h3>
        <span className="ml-auto text-[10px] text-muted font-mono">L{card.lines.join(', ')}{card.timestamp && ` · ${card.timestamp}`}</span>
      </div>
      <CollapsibleText text={card.text} />
      <details className="mt-2 text-[11px] text-muted">
        <summary className="cursor-pointer">原始记录</summary>
        <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-[11px] leading-5">{card.lines.map((line) => lines[line - 1]?.raw || '').join('\n')}</pre>
      </details>
    </article>
  );
}

function ToolCard({ tool, sequence, highlighted }: { tool: TranscriptTool; sequence: number; highlighted: boolean }) {
  const labels = { success: '已完成', error: '执行失败', incomplete: '未记录结果', orphan: '未匹配请求' };
  const statusClass = tool.status === 'success' ? 'bg-emerald-50 text-emerald-700' : tool.status === 'error' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700';
  return (
    <article id={`transcript-tool-${sequence}`} data-source-lines={[...tool.requestLines, ...tool.resultLines].join(',')} className={`rounded-xl border p-4 ${highlighted ? 'border-accent bg-orange-50/30' : 'border-line bg-white'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-md bg-orange-100 text-accent text-sm font-semibold">{sequence}</span>
        <h3 className="text-sm font-semibold">{tool.name}</h3>
        <span className={`px-2 py-1 rounded-full text-[10px] ${statusClass}`}>{labels[tool.status]}</span>
      </div>
      <p className="mt-2 text-[10px] font-mono text-muted break-all">tool_use_id: {tool.id} · 请求 {tool.requestLines.length ? `L${tool.requestLines.join(', ')}` : '缺失'} · 结果 {tool.resultLines.length ? `L${tool.resultLines.join(', ')}` : '缺失'}</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <section><h4 className="text-xs font-semibold mb-2">请求参数</h4><CollapsibleText text={tool.requestLines.length ? JSON.stringify(tool.input, null, 2) : '原始记录中没有对应请求。'} /></section>
        <section><h4 className="text-xs font-semibold mb-2">执行结果</h4><CollapsibleText text={tool.resultLines.length ? readableContent(tool.outputs) || '（空结果）' : '原始记录中尚无对应结果。'} /></section>
      </div>
    </article>
  );
}
