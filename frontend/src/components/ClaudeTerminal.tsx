import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

export type SocketState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

export interface TerminalProcessStatus {
  session_id: string;
  state: 'running' | 'exited';
  project_root: string;
  claude_command: string;
  claude_session_id: string;
  active_run_id: string | null;
  full_permissions: boolean;
  exit_code: number | null;
}

export interface ClaudeTerminalHandle {
  interrupt: () => void;
  focus: () => void;
}

interface Props {
  sessionId: string | null;
  onSocketState: (state: SocketState) => void;
  onProcessStatus: (status: TerminalProcessStatus) => void;
  onError: (message: string) => void;
}

const ClaudeTerminal = forwardRef<ClaudeTerminalHandle, Props>(function ClaudeTerminal(
  { sessionId, onSocketState, onProcessStatus, onError },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useImperativeHandle(ref, () => ({
    interrupt() {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'interrupt' }));
      }
    },
    focus() {
      terminalRef.current?.focus();
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

    const fit = () => {
      try {
        fitAddon.fit();
        const socket = socketRef.current;
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({
            type: 'resize',
            rows: terminal.rows,
            cols: terminal.cols,
          }));
        }
      } catch {
        // The terminal can briefly have zero dimensions while switching pages.
      }
    };
    const observer = new ResizeObserver(fit);
    observer.observe(containerRef.current);
    requestAnimationFrame(fit);

    const inputSubscription = terminal.onData((data) => {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    return () => {
      observer.disconnect();
      inputSubscription.dispose();
      terminal.dispose();
      terminalRef.current = null;
      fitRef.current = null;
    };
  }, []);

  useEffect(() => {
    const terminal = terminalRef.current;
    if (!sessionId || !terminal) {
      onSocketState('idle');
      return;
    }

    terminal.reset();
    terminal.write('\x1b[38;5;244mConnecting to local Claude Code terminal...\x1b[0m\r\n');
    onSocketState('connecting');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/terminal/${sessionId}`);
    socketRef.current = socket;

    socket.onopen = () => {
      onSocketState('connected');
      const activeTerminal = terminalRef.current;
      if (activeTerminal) {
        socket.send(JSON.stringify({
          type: 'resize',
          rows: activeTerminal.rows,
          cols: activeTerminal.cols,
        }));
        activeTerminal.focus();
      }
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'output') {
          terminal.write(message.data ?? '');
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
      onSocketState('error');
      onError('Cannot connect to the local terminal service');
    };
    socket.onclose = () => {
      onSocketState('disconnected');
      if (socketRef.current === socket) socketRef.current = null;
    };

    return () => {
      socket.close();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [sessionId, onError, onProcessStatus, onSocketState]);

  return (
    <div className="h-full min-h-0 rounded-2xl overflow-hidden bg-[#171411] border border-[#3c342d] shadow-2xl">
      <div ref={containerRef} className="h-full w-full p-3" />
    </div>
  );
});

export default ClaudeTerminal;
