import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { StableTerminalResize } from '../utils/terminalResize';
import '@xterm/xterm/css/xterm.css';

export type SocketState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

export interface TerminalProcessStatus {
  session_id: string;
  state: 'running' | 'exited';
  project_root: string;
  claude_command: string;
  claude_session_id: string;
  active_run_id: string | null;
  observer_session_id: string;
  observer_status: 'recording' | 'processing' | 'ready' | 'failed';
  observer_derived: boolean;
  observer_error: string | null;
  full_permissions: boolean;
  exit_code: number | null;
}

export interface ClaudeTerminalHandle {
  interrupt: () => void;
  focus: () => void;
  redraw: () => void;
  getSize: () => { rows: number; cols: number } | undefined;
}

interface Props {
  sessionId: string | null;
  visible: boolean;
  resizeOwnership: boolean;
  onSocketState: (state: SocketState) => void;
  onProcessStatus: (status: TerminalProcessStatus) => void;
  onError: (message: string) => void;
}

const ClaudeTerminal = forwardRef<ClaudeTerminalHandle, Props>(function ClaudeTerminal(
  { sessionId, visible, resizeOwnership, onSocketState, onProcessStatus, onError },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const [replaying, setReplaying] = useState(false);
  const replayingRef = useRef(false);
  const socketRef = useRef<WebSocket | null>(null);
  const resizeGateRef = useRef(new StableTerminalResize());
  const fitCallbackRef = useRef<(() => void) | null>(null);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const resizeOwnershipRef = useRef(resizeOwnership);
  resizeOwnershipRef.current = resizeOwnership;

  useImperativeHandle(ref, () => ({
    interrupt() {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'interrupt' }));
      }
    },
    redraw() {
      const socket=socketRef.current;
      if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'input',data:'\x0c'}));
    },
    focus() {
      terminalRef.current?.focus();
    },
    getSize() {
      const proposed=fitRef.current?.proposeDimensions();
      const terminal=terminalRef.current;
      return proposed && proposed.rows>=2 && proposed.cols>=10 ? proposed
        : terminal ? {rows:terminal.rows,cols:terminal.cols} : undefined;
    },
  }), []);

  useEffect(() => {
    if (!containerRef.current) return;

    const terminal = new Terminal({
      cursorBlink: true,
      cursorStyle: 'bar',
      convertEol: false,
      scrollback: 20_000,
      fontFamily: 'Consolas, "Cascadia Mono", monospace',
      fontSize: 14,
      lineHeight: 1.16,
      letterSpacing: 0,
      allowTransparency: true,
      theme: {
        background: '#171411',
        foreground: '#f4eadf',
        cursor: '#e7925d',
        selectionBackground: '#7a4c3377',
        black: '#171411',
        red: '#e06c75',
        green: '#98c379',
        yellow: '#e5c07b',
        blue: '#61afef',
        magenta: '#c678dd',
        cyan: '#56b6c2',
        white: '#f4eadf',
        brightBlack: '#665f58',
      },
    });
    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.open(containerRef.current);
    terminalRef.current = terminal;
    fitRef.current = fitAddon;

    let fitTimer: ReturnType<typeof setTimeout> | undefined;
    const fit = () => {
      clearTimeout(fitTimer);
      const container = containerRef.current;
      if (!visibleRef.current || document.hidden || !container || container.clientWidth <= 0 || container.clientHeight <= 0) return;
      try {
        const proposed=fitAddon.proposeDimensions();
        if (!proposed) return;
        const size=resizeGateRef.current.offer(proposed,performance.now());
        if (size) {
          if (terminal.cols!==size.cols || terminal.rows!==size.rows) terminal.resize(size.cols,size.rows);
          const socket=socketRef.current;
          if (socket?.readyState===WebSocket.OPEN) socket.send(JSON.stringify({type:'resize',...size}));
        }
        if (resizeGateRef.current.pending) fitTimer=setTimeout(fit,120);
      } catch { /* A hidden or transitioning panel may briefly have no usable grid. */ }
    };
    fitCallbackRef.current = fit;
    const scheduleFit = () => {
      if (resizeOwnershipRef.current && document.hidden && socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: 'deactivate' }));
      }
      fit();
    };
    const observer = new ResizeObserver(scheduleFit);
    observer.observe(containerRef.current);
    const fitFrame = requestAnimationFrame(fit);
    window.addEventListener('resize', scheduleFit);
    window.addEventListener('focus', scheduleFit);
    document.addEventListener('visibilitychange', scheduleFit);
    let disposed = false;
    void document.fonts.ready.then(() => { if (!disposed) scheduleFit(); });

    const inputSubscription = terminal.onData((data) => {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN && !replayingRef.current) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(fitFrame);
      clearTimeout(fitTimer);
      window.removeEventListener('resize', scheduleFit);
      window.removeEventListener('focus', scheduleFit);
      document.removeEventListener('visibilitychange', scheduleFit);
      observer.disconnect();
      inputSubscription.dispose();
      terminal.dispose();
      terminalRef.current = null;
      fitRef.current = null;
      fitCallbackRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!visible) {
      if (resizeOwnershipRef.current && socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'deactivate' }));
      return;
    }
    const frame = requestAnimationFrame(() => fitCallbackRef.current?.());
    return () => cancelAnimationFrame(frame);
  }, [visible, resizeOwnership]);

  useEffect(() => {
    const terminal = terminalRef.current;
    if (!sessionId || !terminal) {
      onSocketState('idle');
      return;
    }

    const size=fitRef.current?.proposeDimensions();
    if(size && size.rows>=2 && size.cols>=10)terminal.resize(size.cols,size.rows);
    replayingRef.current=false;setReplaying(false);
    terminal.reset();
    terminal.write('\x1b[38;5;244mConnecting to local Claude Code terminal...\x1b[0m\r\n');
    onSocketState('connecting');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/terminal/${sessionId}`);
    socketRef.current = socket;

    socket.onopen = () => {
      if(socketRef.current!==socket){socket.close();return;}
      onSocketState('connected');
      resizeGateRef.current.reset();
      fitCallbackRef.current?.();
      const activeTerminal = terminalRef.current;
      if (activeTerminal && visibleRef.current) {
        activeTerminal.focus();
      }
    };
    socket.onmessage = (event) => {
      if(socketRef.current!==socket)return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'output') {
          if(message.replay){
            replayingRef.current=true;setReplaying(true);
            terminal.write(message.data??'',()=>{
              if(socketRef.current!==socket)return;
              replayingRef.current=false;setReplaying(false);terminal.refresh(0,terminal.rows-1);
            });
          }else terminal.write(message.data ?? '');
        } else if (message.type === 'status') {
          onProcessStatus(message as TerminalProcessStatus);
        } else if (message.type === 'error') {
          onError(message.message ?? 'Terminal connection failed');
        }
      } catch {
        onError('The terminal service returned an invalid message');
      }
    };
    socket.onerror = () => {
      if(socketRef.current!==socket)return;
      onSocketState('error');
      onError('Cannot connect to the local terminal service');
    };
    socket.onclose = () => {
      if(socketRef.current!==socket)return;
      replayingRef.current=false;setReplaying(false);
      onSocketState('disconnected');
      if (socketRef.current === socket) socketRef.current = null;
    };

    return () => {
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [sessionId, onError, onProcessStatus, onSocketState]);

  return (
    <div onPointerDown={() => {
      if (resizeOwnershipRef.current && socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: 'activate' }));
    }} className="relative h-full w-full min-h-0 min-w-0 rounded-xl overflow-hidden bg-[#171411] border border-[#3c342d] shadow-2xl">
      {replaying && <div role="status" className="absolute inset-0 z-10 flex items-center justify-center bg-[#171411] text-xs text-stone-300">恢复终端画面…</div>}
      <div className="h-full w-full min-h-0 min-w-0 p-2"><div ref={containerRef} className="h-full w-full min-h-0 min-w-0 overflow-hidden" /></div>
    </div>
  );
});

export default ClaudeTerminal;
