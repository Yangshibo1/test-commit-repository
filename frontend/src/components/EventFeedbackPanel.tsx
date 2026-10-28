import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface Feedback {
  feedback_id: string;
  event_sequence: number;
  event_title: string;
  prompt: string;
  status: 'draft' | 'sending' | 'submitted' | 'delivery_uncertain';
  submitted_at?: string;
}
interface Delivery { can_send: boolean; terminal_session_id: string | null; reason: string }
interface FeedbackResponse { feedback: Feedback; delivery?: Delivery }

async function readResponse(response: Response): Promise<FeedbackResponse> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `请求失败（HTTP ${response.status}）`);
  return body;
}

export default function EventFeedbackPanel({ sessionId, eventId, sequence, title }: {
  sessionId: string; eventId: string; sequence: number; title: string;
}) {
  const storageKey = `agentvast:event-feedback:${sessionId}:${eventId}`;
  const [saved] = useState<{content?: string; feedback?: Feedback} | null>(() => {
    try { return JSON.parse(sessionStorage.getItem(storageKey) || 'null'); }
    catch { return null; }
  });
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(saved?.content || '');
  const [feedback, setFeedback] = useState<Feedback | null>(saved?.feedback || null);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const root = `/api/observations/${encodeURIComponent(sessionId)}`;

  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify({content,feedback})); }
    catch { /* The server still retains every prepared feedback record. */ }
  }, [storageKey, content, feedback]);

  useEffect(() => {
    if (!open || busy || !feedback || feedback.status !== 'draft') return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await readResponse(await fetch(`${root}/event-feedback/${feedback.feedback_id}`, {cache:'no-store'}));
        if (active) { setFeedback(result.feedback); setDelivery(result.delivery || null); }
      } catch { /* Keep the draft; sending always rechecks the target session. */ }
      finally { if (active) timer = setTimeout(poll, 2000); }
    };
    timer = setTimeout(poll, 2000);
    return () => { active = false; clearTimeout(timer); };
  }, [root, open, busy, feedback?.feedback_id, feedback?.status]);

  const preview = async () => {
    setBusy(true); setError(''); setCopied(false);
    try {
      const result = await readResponse(await fetch(`${root}/events/${encodeURIComponent(eventId)}/feedback`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content}),
      }));
      setFeedback(result.feedback); setDelivery(result.delivery || null);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const send = async () => {
    if (!feedback || !delivery?.terminal_session_id) return;
    setBusy(true); setError('');
    try {
      const result = await readResponse(await fetch(`${root}/event-feedback/${feedback.feedback_id}/send`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({terminal_session_id:delivery.terminal_session_id}),
      }));
      setFeedback(result.feedback);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // Reconcile an ambiguous network response with the persisted delivery
      // state, rather than treating a failed response as permission to resend.
      try {
        const result = await readResponse(await fetch(`${root}/event-feedback/${feedback.feedback_id}`,{cache:'no-store'}));
        setFeedback(result.feedback); setDelivery(result.delivery || null);
      } catch { setDelivery(null); }
    } finally { setBusy(false); }
  };
  const submitted = feedback?.status === 'submitted';
  const uncertain = feedback && ['sending','delivery_uncertain'].includes(feedback.status);
  return <>
    <button type="button" className="semantic-button w-full justify-center" onClick={() => setOpen(true)}>提出修改意见</button>
    {submitted && <p className="text-xs text-teal-700" role="status">此 Event 的修改意见已发送给 Claude</p>}
    {open && createPortal(<div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/30 p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="event-feedback-title" className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-[#fffdfb] shadow-xl"
        onKeyDown={e => {
          if (e.key === 'Escape' && !busy) { e.stopPropagation(); setOpen(false); }
          if (e.key !== 'Tab') return;
          const focusable = e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),textarea:not(:disabled),[tabindex="0"]');
          const first = focusable[0], last = focusable[focusable.length-1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }}>
        <div className="flex items-start gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1"><h2 id="event-feedback-title" className="font-semibold">针对 Event {sequence} 提出修改意见</h2><p className="mt-1 text-sm text-muted break-words">{title}</p></div>
          <button type="button" autoFocus disabled={busy} className="semantic-dismiss" aria-label="关闭修改意见" onClick={() => setOpen(false)}>×</button>
        </div>
        <div className="min-h-0 overflow-auto px-5 py-4 space-y-4">
          <p className="text-xs leading-5 text-muted">附带此事件的执行事实、所属任务、关联文件及已有 AI 摘要，发送给同一 Claude 会话，引导后续工作。</p>
          <label className="block text-sm font-medium" htmlFor="event-feedback-content">修改意见</label>
          <textarea id="event-feedback-content" rows={4} maxLength={6000} disabled={busy || !!submitted || !!uncertain}
            value={content} onChange={e => { setContent(e.target.value); setFeedback(null); setDelivery(null); setError(''); setCopied(false); }}
            placeholder="例如：这里应先排除重复记录再计算均值，请重做受影响的统计，并更新图表与结论。"
            className="w-full resize-y rounded-xl border border-line bg-white p-3 text-sm leading-6 outline-none focus:border-accent disabled:bg-stone-50" />
          {!feedback && <button type="button" className="semantic-button" disabled={busy || !content.trim()} onClick={() => void preview()}>{busy ? '整理上下文…' : '预览修改 Prompt'}</button>}
          {feedback && <div className="space-y-2">
            <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{submitted ? '已发送的 Prompt' : '将发送的完整 Prompt'}</h3>
              <button type="button" className="semantic-button semantic-button-small" onClick={() => {
                void navigator.clipboard.writeText(feedback.prompt).then(() => setCopied(true)).catch(() => setError('复制失败，可在下方选中文本复制'));
              }}>{copied ? '已复制' : '复制 Prompt'}</button>
            </div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-line bg-stone-50 p-3 text-xs leading-5" tabIndex={0}>{feedback.prompt}</pre>
            <p className="text-xs text-muted break-all">会话：{sessionId}</p>
            {submitted ? <p role="status" className="text-sm text-teal-700">已提交给 Claude，作为新一轮用户消息。请在“Claude 运行”查看执行进展。</p>
              : uncertain ? <p role="status" className="text-sm text-amber-700">投递状态未确认，请先查看 Claude 终端，避免重复发送。</p>
              : <p role="status" className="text-xs text-muted">{delivery?.reason || '暂时无法读取终端状态，请关闭后重新打开预览'}</p>}
          </div>}
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-line px-5 py-3">
          {submitted && <button type="button" className="semantic-button" onClick={() => { setContent(''); setFeedback(null); setDelivery(null); setError(''); setCopied(false); }}>再提一条意见</button>}
          <button type="button" className="semantic-button" disabled={busy} onClick={() => setOpen(false)}>{submitted ? '完成' : '关闭'}</button>
          {feedback && !submitted && !uncertain && <button type="button" className="semantic-button semantic-button-accent" disabled={busy || !delivery?.can_send} onClick={() => void send()}>{busy ? '发送中…' : '发送给当前 Agent'}</button>}
        </div>
      </section>
    </div>,document.body)}
  </>;
}
