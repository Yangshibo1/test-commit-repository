"""Local Web terminal for an interactive Claude Code CLI process.

The Web terminal is intentionally transport-only. AgentVAST workflow records
continue to be written through the structured CLI / Hook path, never inferred
from terminal text.
"""

import asyncio
import codecs
import errno
import functools
import json
import mimetypes
import os
import re
import signal
import shutil
import struct
import subprocess
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from agentvast.paths import (
    expose_repository_to_python,
    resolve_user_path,
    workflow_database,
)
from agentvast.observer.trace_builder import (
    list_observer_sessions,
    load_observer_trace,
)
from agentvast.observer.live_trace import (LiveTraceService, enable_live_trace, live_state,
    sync_live_trace, live_event_workflow, retry_live_turns, request_turn_analysis)
from agentvast.observer.event_merger import derive_session
from agentvast.observer.event_feedback import (
    build_feedback, save_feedback, read_feedback, claim_feedback,
)
from agentvast.observer.store import (
    create_session as create_observer_session,
    default_observations_root,
    register_session_root,
    read_manifest,
    update_manifest,
    utc_now,
    session_directory,
)
from agentvast.observer.transcript_reader import finalize_session as finalize_observer_session
from agentvast.observer.validation import validate_session as validate_observer_session
from agentvast.workflow_store import WorkflowError, WorkflowStore

MAX_REPLAY_CHARACTERS = 2_000_000
DEFAULT_AUTO_COMPACT_WINDOW = 200_000
DEFAULT_AUTO_COMPACT_PERCENT = 80
DEFAULT_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "claude-observer-plugin"


class WebDependencyError(RuntimeError):
    """Raised when optional Web terminal dependencies are unavailable."""


class _PosixPtyProcess:
    """POSIX PTY adapter exposing the pywinpty methods used by TerminalSession."""

    def __init__(self, pid: int, master_fd: int) -> None:
        self.pid = pid
        self.master_fd = master_fd
        self.closed = False
        self.exitstatus: Optional[int] = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._wait_lock = threading.Lock()

    @classmethod
    def spawn(
        cls,
        arguments: List[str],
        *,
        cwd: str,
        env: Dict[str, str],
        dimensions: Tuple[int, int],
    ) -> "_PosixPtyProcess":
        import fcntl
        import termios

        master_fd, slave_fd = os.openpty()
        # Set geometry before the child can render its initial terminal screen.
        size = struct.pack("HHHH", int(dimensions[0]), int(dimensions[1]), 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, size)
        pid = os.fork()
        if pid == 0:
            try:
                os.close(master_fd)
                os.setsid()
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                for descriptor in (0, 1, 2):
                    os.dup2(slave_fd, descriptor)
                if slave_fd > 2:
                    os.close(slave_fd)
                os.chdir(cwd)
                os.execvpe(arguments[0], arguments, env)
            except BaseException as error:
                try:
                    os.write(2, "Terminal process failed to start: {0}\n".format(error).encode())
                finally:
                    os._exit(127)

        os.close(slave_fd)
        process = cls(pid, master_fd)
        process.setwinsize(*dimensions)
        return process

    def _collect_exit(self, block: bool = False) -> bool:
        if self.exitstatus is not None:
            return True
        with self._wait_lock:
            if self.exitstatus is not None:
                return True
            try:
                waited_pid, status = os.waitpid(self.pid, 0 if block else os.WNOHANG)
            except ChildProcessError:
                return self.exitstatus is not None
            if waited_pid == 0:
                return False
            if os.WIFEXITED(status):
                self.exitstatus = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                self.exitstatus = -os.WTERMSIG(status)
            else:
                self.exitstatus = 1
            return True

    def isalive(self) -> bool:
        return not self._collect_exit()

    def read(self, size: int = 4096) -> str:
        if self.closed:
            raise EOFError
        try:
            value = os.read(self.master_fd, size)
        except OSError as error:
            if error.errno in {errno.EIO, errno.EBADF}:
                self._collect_exit()
                raise EOFError from error
            raise
        if not value:
            self._collect_exit()
            raise EOFError
        return self._decoder.decode(value)

    def write(self, data: str) -> int:
        if self.closed:
            raise EOFError
        encoded = data.encode("utf-8")
        written = 0
        while written < len(encoded):
            try:
                count = os.write(self.master_fd, encoded[written:])
            except InterruptedError:
                continue
            if count <= 0:
                raise EOFError
            written += count
        return written

    def setwinsize(self, rows: int, cols: int) -> None:
        import fcntl
        import termios

        if self.closed:
            return
        size = struct.pack("HHHH", int(rows), int(cols), 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)

    def sendintr(self) -> None:
        if self.isalive():
            os.killpg(self.pid, signal.SIGINT)

    def close(self, force: bool = True) -> None:
        if self.closed:
            return
        if self.isalive():
            try:
                os.killpg(self.pid, signal.SIGHUP if force else signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        self.closed = True
        if not self._collect_exit():
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._collect_exit(block=True)


def _spawn_terminal_process(
    arguments: List[str],
    *,
    cwd: str,
    env: Dict[str, str],
    dimensions: Tuple[int, int],
) -> Any:
    if sys.platform == "win32":
        try:
            from winpty import PtyProcess
        except ImportError as error:
            raise WebDependencyError(
                'pywinpty is not installed. Run: python -m pip install -e ".[web]"'
            ) from error
        return PtyProcess.spawn(arguments, cwd=cwd, env=env, dimensions=dimensions)
    if os.name == "posix":
        return _PosixPtyProcess.spawn(
            arguments,
            cwd=cwd,
            env=env,
            dimensions=dimensions,
        )
    raise WebDependencyError("Interactive Web terminals are unsupported on this platform")


def _load_web_dependencies() -> Tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, StreamingResponse
        from pydantic import BaseModel
    except ImportError as error:
        raise WebDependencyError(
            "AgentVAST Web dependencies are not installed. "
            'Run: python -m pip install -e ".[web]"'
        ) from error
    return (
        FastAPI,
        HTTPException,
        WebSocket,
        WebSocketDisconnect,
        CORSMiddleware,
        FileResponse,
        StreamingResponse,
        BaseModel,
    )


def _resolve_observer_artifact_file(trace: Dict[str, Any], artifact_id: str) -> Path:
    artifact = next(
        (
            item
            for item in trace.get("artifacts") or []
            if isinstance(item, dict) and item.get("artifact_id") == artifact_id
        ),
        None,
    )
    if artifact is None:
        raise FileNotFoundError("Observed artifact does not exist: {0}".format(artifact_id))
    cwd_value = str((trace.get("session") or {}).get("cwd") or "").strip()
    if not cwd_value:
        raise FileNotFoundError("Observation has no project directory")
    project_root = Path(cwd_value).resolve()
    candidate = Path(str(artifact.get("path") or ""))
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise PermissionError("Observed artifact is outside the project directory") from error
    if not candidate.is_file():
        raise FileNotFoundError("Observed artifact file is no longer available")
    return candidate


def _open_local_file(path: Path) -> None:
    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("Windows local-file opener is unavailable")
        startfile(str(path))
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _resolve_claude(command: str) -> str:
    value = str(command or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    if not value:
        raise FileNotFoundError("Claude Code executable path is empty")
    expanded = os.path.expandvars(value)
    candidate = Path(expanded).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(expanded)
    if resolved is None:
        raise FileNotFoundError(
            "Claude Code executable was not found: {0}. Enter 'claude' or an "
            "existing full path to claude.exe/claude.cmd.".format(value)
        )
    return resolved


def _pty_arguments(
    command: str,
    claude_session_id: str,
    plugin_dir: Path,
    resume: bool,
) -> list:
    resolved = _resolve_claude(command)
    arguments = [resolved, "--dangerously-skip-permissions"]
    arguments.extend(
        [
            "--resume" if resume else "--session-id",
            claude_session_id,
            "--plugin-dir",
            str(plugin_dir),
        ]
    )

    # Windows CreateProcess cannot directly execute a .cmd/.bat shim. Claude
    # installations created by npm commonly expose exactly such a shim.
    if Path(resolved).suffix.lower() in {".cmd", ".bat"}:
        command_processor = os.environ.get("COMSPEC", "cmd.exe")
        return [command_processor, "/d", "/s", "/c", *arguments]
    return arguments


def _activation_prompt(result: Dict[str, Any], task: str) -> str:
    declared_files = (
        "\n".join("- {0}".format(item["path"]) for item in result["initial_file_versions"])
        or "- No initial files were declared."
    )
    discovery_instruction = (
        "No initial file was supplied. You may use Glob, Grep, and Read to understand "
        "the task before set-plan. After a Node starts, use any relevant accessible "
        "file normally and list the files actually used in complete-node; AgentVAST "
        "will observe and register previously unknown external inputs then."
        if not result["initial_file_versions"]
        else "The supplied files are initial context, not an input whitelist. After "
        "a Node starts, you may use other relevant accessible files and record the "
        "files actually used in complete-node."
    )
    return (
        "[AGENTVAST_ACTIVATE run_id={0}]\n"
        "Begin the following recorded data-analysis task:\n{1}\n\n"
        "Declared input files:\n{2}\n\n"
        "{3}\n\n"
        "AgentVAST records the workflow; you perform the analysis. Write every "
        "Plan Node objective in Chinese. Before material analysis, use "
        "python -m agentvast.agent_cli set-plan with semantic Nodes. After set-plan, "
        "print the task and the complete returned Plan in the terminal. The stable "
        "node IDs, Chinese objectives, dependencies, and required artifact types "
        "must exactly match the structured Plan shown in AgentVAST Web; do not "
        "translate, paraphrase, omit, or add Nodes. End with: "
        "'Plan 已生成，请在右侧查看、编辑或确认。' Stop for Web approval. After "
        "approval, run each Node with start-node and complete-node. Whenever findings "
        "change the path, revise only future pending Nodes, print the complete new "
        "Revision in the same format, and stop for Web editing or approval again "
        "before material work continues. Save real artifacts under {4}. When all "
        "current Plan Nodes are complete, end the turn and keep this Run active for "
        "follow-up analysis; do not call finish-run automatically. Do not use "
        "AgentVAST MCP tools."
    ).format(
        result["run_id"],
        task,
        declared_files,
        discovery_instruction,
        result["result_root"],
    )


def _continuation_prompt(run_id: str, state: Dict[str, Any]) -> str:
    completed = [
        {
            "node_id": node["node_id"],
            "objective": node["objective"],
            "result_summary": node.get("result_summary"),
            "analysis_conclusion": node.get("analysis_conclusion"),
        }
        for node in state["nodes"]
        if node["status"] == "completed"
    ]
    active = next(
        (node for node in state["nodes"] if node["status"] == "active"),
        None,
    )
    recovery = {
        "task": state["run"]["task_description"],
        "plan": state["plan"],
        "completed_nodes": completed,
        "active_node": active,
        "pending_user_inputs": state["pending_user_inputs"],
        "result_root": state["run"]["result_root"],
    }
    return (
        "[AGENTVAST_CONTINUATION_TASK run_id={0}]\n"
        "Continue this active AgentVAST Run in a fresh Claude session. SQLite is "
        "the workflow source of truth. Do not redo completed Nodes or rewrite "
        "their Plan definitions. Their recorded artifacts may still be used or "
        "edited by later Nodes with truthful versioned input/output recording. "
        "Inspect existing artifacts before continuing an active Node. Resolve any "
        "pending user input using the exact recorder commands, revise only future "
        "pending Nodes when required, and finish the remaining real analysis.\n\n"
        "Recovery state:\n{1}"
    ).format(run_id, json.dumps(recovery, ensure_ascii=False))


async def _send_control_message(
    session: "TerminalSession",
    store: WorkflowStore,
    run_id: str,
    kind: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Store full control data in SQLite and type only a short nonce into PTY."""

    control = store.create_control_message(
        run_id,
        session.claude_session_id,
        kind,
        payload,
    )
    await session.write("[AGENTVAST_CONTROL id={0}]".format(control["control_id"]))
    # Claude Code treats text and Enter written in one PTY chunk as a paste in
    # some terminal states. Send a distinct key event so Web actions execute.
    await asyncio.sleep(0.12)
    await session.write("\r")
    return control


class TerminalSession:
    def __init__(
        self,
        process: Any,
        project_root: Path,
        claude_command: str,
        full_permissions: bool,
        claude_session_id: str,
        database_path: Path,
        observer_root: Path,
    ) -> None:
        self.session_id = "terminal_{0}".format(uuid.uuid4().hex[:12])
        self.process = process
        self.project_root = project_root
        self.claude_command = claude_command
        self.full_permissions = full_permissions
        self.claude_session_id = claude_session_id
        self.database_path = database_path
        self.observer_session_id = claude_session_id
        self.observer_root = observer_root
        self.observer_status = "recording"
        self.observer_error: Optional[str] = None
        self.observer_derived = False
        self._history: Deque[str] = deque()
        self._history_characters = 0
        self._subscribers: Set[asyncio.Queue] = set()
        self._client_sizes: Dict[asyncio.Queue, Tuple[int, int]] = {}
        self._size_owner: Optional[asyncio.Queue] = None
        self._size_lock = asyncio.Lock()
        self._input_lock = asyncio.Lock()
        self.input_pending = False
        self._applied_size: Optional[Tuple[int, int]] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._finalize_task: Optional[asyncio.Task] = None
        self._finalize_lock = asyncio.Lock()
        self._closing = False

    def start_reader(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_output())

    def is_alive(self) -> bool:
        try:
            return bool(self.process.isalive())
        except Exception:
            return False

    def status(self) -> Dict[str, Any]:
        alive = self.is_alive()
        exit_code = None
        if not alive:
            try:
                exit_code = self.process.exitstatus
            except Exception:
                exit_code = None
        active_run = (
            WorkflowStore(self.database_path).active_run_for_session(self.claude_session_id)
            if self.database_path.is_file()
            else None
        )
        return {
            "session_id": self.session_id,
            "state": "running" if alive else "exited",
            "project_root": str(self.project_root),
            "claude_command": self.claude_command,
            "claude_session_id": self.claude_session_id,
            "full_permissions": self.full_permissions,
            "exit_code": exit_code,
            "active_run_id": active_run["run_id"] if active_run else None,
            "observer_session_id": self.observer_session_id,
            "observer_status": self.observer_status,
            "observer_derived": self.observer_derived,
            "observer_error": self.observer_error,
            "input_pending": self.input_pending,
        }

    def subscribe(self) -> Tuple[asyncio.Queue, str]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue, "".join(self._history)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
        self.release_size(queue)

    def release_size(self, queue: asyncio.Queue) -> None:
        self._client_sizes.pop(queue, None)
        if self._size_owner is queue:
            self._size_owner = None

    async def claim_size(self, queue: asyncio.Queue) -> None:
        self._size_owner = queue
        dimensions = self._client_sizes.get(queue)
        if dimensions:
            await self.resize(*dimensions, client=queue)

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            await queue.put(message)

    def _remember(self, output: str) -> None:
        if not output:
            return
        self._history.append(output)
        self._history_characters += len(output)
        while self._history_characters > MAX_REPLAY_CHARACTERS and self._history:
            removed = self._history.popleft()
            self._history_characters -= len(removed)

    async def _read_output(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self.is_alive() and not self._closing:
                try:
                    output = await loop.run_in_executor(None, self.process.read, 4096)
                except EOFError:
                    break
                except Exception as error:
                    if not self._closing:
                        await self._broadcast(
                            {"type": "error", "message": "Terminal read failed: {0}".format(error)}
                        )
                    break
                if output:
                    self._remember(output)
                    await self._broadcast({"type": "output", "data": output})
        finally:
            await self.finalize_observation()
            await self._broadcast({"type": "status", **self.status()})

    async def finalize_observation(self) -> None:
        async with self._finalize_lock:
            if self.observer_status in {"ready", "failed"}:
                return
            self.observer_status = "processing"
            loop = asyncio.get_running_loop()

            def process() -> None:
                if read_manifest(self.observer_session_id, self.observer_root).get("live_trace_enabled"):
                    update_manifest(self.observer_session_id, {"ended_at": utc_now()}, self.observer_root)
                    sync_live_trace(self.observer_session_id, self.observer_root, settle_seconds=0)
                else:
                    result = finalize_observer_session(self.observer_session_id, self.observer_root)
                    if result.get("transcript") is None:
                        warnings = result.get("warnings") or []
                        raise RuntimeError("; ".join(str(item) for item in warnings))
                derive_session(self.observer_session_id, str(self.observer_root))
                validate_observer_session(self.observer_session_id, str(self.observer_root))

            try:
                await loop.run_in_executor(None, process)
                self.observer_status = "ready"
                self.observer_derived = True
                self.observer_error = None
            except Exception as error:
                self.observer_status = "failed"
                self.observer_error = str(error)

    async def write(self, data: str) -> None:
        async with self._input_lock:
            await self._write_unlocked(data)
            if "\x1b[200~" in data:
                self.input_pending = True
            elif any(c in data for c in ("\r", "\x15", "\x03")):
                self.input_pending = bool(data.rsplit("\r", 1)[-1].strip()) if "\r" in data else False
            elif any(c.isprintable() for c in re.sub(r"\x1b(?:\[[0-9;?]*[A-Za-z~]|\][^\x07\x1b]*(?:\x07|\x1b\\))", "", data)):
                self.input_pending = True

    async def _write_unlocked(self, data: str) -> None:
        if not self.is_alive():
            raise RuntimeError("Claude process is not running")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.process.write, data)

    async def submit_prompt(self, prompt: str) -> None:
        """Paste one multiline prompt, then submit without interleaved keystrokes."""
        async with self._input_lock:
            if self.input_pending:
                raise RuntimeError("Claude 终端有未提交输入，请先提交或用 Ctrl+U 清空")
            self.input_pending = True
            await self._write_unlocked("\x1b[200~" + prompt + "\x1b[201~")
            await asyncio.sleep(0.12)
            await self._write_unlocked("\r")
            self.input_pending = False

    async def resize(self, rows: int, cols: int, client: Optional[asyncio.Queue] = None) -> None:
        if not self.is_alive():
            return
        rows = max(2, min(rows, 500))
        cols = max(10, min(cols, 1000))
        async with self._size_lock:
            if client is not None:
                self._client_sizes[client] = (rows, cols)
                if self._size_owner is not None and self._size_owner is not client:
                    return
                if self._size_owner is None:
                    # Before interaction, a small observer must not shrink a larger view.
                    rows, cols = max(self._client_sizes.values(), key=lambda size: size[0] * size[1])
            loop = asyncio.get_running_loop()
            if self._applied_size == (rows, cols):
                return
            await loop.run_in_executor(None, self.process.setwinsize, rows, cols)
            self._applied_size = (rows, cols)

    async def interrupt(self) -> None:
        if not self.is_alive():
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.process.sendintr)
        self.input_pending = False

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if not getattr(self.process, "closed", False):
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, self.process.close, True)
            except Exception:
                # The process may have exited between the status check and close.
                pass
        await self.finalize_observation()
        await self._broadcast({"type": "status", **self.status()})


class TerminalManager:
    def __init__(
        self,
        default_project: Path,
        default_claude_command: str,
        plugin_dir: Path,
    ) -> None:
        self.default_project = default_project
        self.default_claude_command = default_claude_command
        self.plugin_dir = plugin_dir
        self.current: Optional[TerminalSession] = None
        self._lock = asyncio.Lock()

    async def create(
        self,
        project_root: Optional[str],
        rows: int,
        cols: int,
        claude_command: Optional[str],
        full_permissions: bool,
        resume_claude_session_id: Optional[str] = None,
        fresh_run_id: Optional[str] = None,
    ) -> TerminalSession:
        async with self._lock:
            if self.current is not None and self.current.is_alive():
                raise RuntimeError("A Claude terminal is already running")
            if (
                self.current is not None
                and self.current.database_path.is_file()
                and not (resume_claude_session_id or fresh_run_id)
            ):
                previous_store = WorkflowStore(self.current.database_path)
                previous_run = previous_store.active_run_for_session(self.current.claude_session_id)
                if previous_run is not None:
                    raise RuntimeError(
                        "The previous Claude process has an active AgentVAST Run. "
                        "Resume the original session or continue the Run in a fresh session."
                    )
            if self.current is not None:
                await self.current.close()

            project = resolve_user_path(project_root) if project_root else self.default_project
            if not project.is_dir():
                raise FileNotFoundError("Project directory does not exist: {0}".format(project))
            if not self.plugin_dir.is_dir():
                raise FileNotFoundError(
                    "AgentVAST plugin directory does not exist: {0}".format(self.plugin_dir)
                )
            if resume_claude_session_id and fresh_run_id:
                raise RuntimeError(
                    "resume_claude_session_id and fresh_run_id are mutually exclusive"
                )

            command = claude_command or self.default_claude_command
            resolved_command = _resolve_claude(command)
            database_path = workflow_database(project)
            store = WorkflowStore(database_path) if database_path.is_file() else None
            recovery_state: Optional[Dict[str, Any]] = None
            if fresh_run_id:
                if store is None:
                    raise RuntimeError("The requested AgentVAST Run database does not exist")
                recovery_state = store.get_state(fresh_run_id)
                if recovery_state["run"]["status"] != "active":
                    raise RuntimeError(
                        "Only an active AgentVAST Run can continue in a fresh session"
                    )
                claude_session_id = str(uuid.uuid4())
                resume = False
            elif resume_claude_session_id:
                claude_session_id = resume_claude_session_id.strip()
                if not claude_session_id:
                    raise RuntimeError("resume Claude session ID cannot be empty")
                resume = True
            else:
                claude_session_id = str(uuid.uuid4())
                resume = False
            arguments = _pty_arguments(
                resolved_command,
                claude_session_id,
                self.plugin_dir,
                resume,
            )
            environment = os.environ.copy()
            environment.setdefault("TERM", "xterm-256color")
            python_directory = str(Path(sys.executable).resolve().parent)
            environment["PATH"] = python_directory + os.pathsep + environment.get("PATH", "")
            expose_repository_to_python(environment)
            environment.update(
                {
                    "AGENTVAST_DB": str(database_path),
                    "AGENTVAST_PROJECT_ROOT": str(project),
                    "AGENTVAST_PYTHON": sys.executable,
                    "AGENTVAST_CLAUDE_SESSION_ID": claude_session_id,
                    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(DEFAULT_AUTO_COMPACT_WINDOW),
                    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": str(DEFAULT_AUTO_COMPACT_PERCENT),
                }
            )
            environment.pop("AGENTVAST_RUN_ID", None)
            environment.pop("AGENTVAST_RESULT_ROOT", None)
            environment.pop("DISABLE_AUTO_COMPACT", None)
            observer_root = default_observations_root()
            observation_directory = session_directory(claude_session_id, observer_root)
            if not (observation_directory / "manifest.json").is_file():
                create_observer_session(
                    claude_session_id,
                    project,
                    observer_root,
                    claude_code_version=None,
                )
            register_session_root(claude_session_id, observer_root)
            enable_live_trace(claude_session_id, observer_root)
            try:
                process = _spawn_terminal_process(
                    arguments,
                    cwd=str(project),
                    env=environment,
                    dimensions=(max(2, min(rows, 500)), max(10, min(cols, 1000))),
                )
            except OSError as error:
                raise RuntimeError(
                    "Claude Code executable was resolved but could not start. "
                    "Executable: {0}; project: {1}; error: {2}".format(
                        resolved_command, project, error
                    )
                ) from error
            self.current = TerminalSession(
                process=process,
                project_root=project,
                claude_command=resolved_command,
                full_permissions=True,
                claude_session_id=claude_session_id,
                database_path=database_path,
                observer_root=observer_root,
            )
            if fresh_run_id and recovery_state is not None:
                assert store is not None
                store.rotate_claude_session(
                    fresh_run_id,
                    claude_session_id,
                    reason="web_fresh_session_recovery",
                    terminal_session_id=self.current.session_id,
                )
            self.current.start_reader()
            if fresh_run_id and recovery_state is not None:
                assert store is not None
                await _send_control_message(
                    self.current,
                    store,
                    fresh_run_id,
                    "fresh_session_recovery",
                    {"instruction": _continuation_prompt(fresh_run_id, recovery_state)},
                )
            return self.current

    def get(self, session_id: str) -> TerminalSession:
        if self.current is None or self.current.session_id != session_id:
            raise KeyError("Terminal session does not exist: {0}".format(session_id))
        return self.current

    async def shutdown(self) -> None:
        if self.current is not None:
            await self.current.close()


def create_app(
    default_project: Path,
    default_claude_command: str = "claude",
    plugin_dir: Path = DEFAULT_PLUGIN_DIR,
) -> Any:
    (
        FastAPI,
        HTTPException,
        WebSocket,
        WebSocketDisconnect,
        CORSMiddleware,
        FileResponse,
        StreamingResponse,
        BaseModel,
    ) = _load_web_dependencies()

    class StartTerminalRequest(BaseModel):
        project_root: Optional[str] = None
        rows: int = 24
        cols: int = 80
        claude_command: Optional[str] = None
        full_permissions: bool = True
        resume_claude_session_id: Optional[str] = None
        fresh_run_id: Optional[str] = None

    class StartRunRequest(BaseModel):
        task: str
        input_files: Optional[List[str]] = None
        checkpoint_mode: str = "plan"

    class PlanApprovalRequest(BaseModel):
        note: str = "用户通过 AgentVAST Web 确认当前 Plan"

    class PlanRevisionRequest(BaseModel):
        nodes: List[Dict[str, Any]]
        change_reason: str = ""

    class InterventionRequest(BaseModel):
        input_type: str
        content: str

    class AbortRunRequest(BaseModel):
        reason: str

    class ReviewRequest(BaseModel):
        force: bool = False

    class SemanticGenerateRequest(BaseModel):
        rules_only: bool = False
        force: bool = False
        resume_inference: Optional[str] = None
        annotation_guidance: str = ""

    class SemanticReviewRequest(BaseModel):
        action: str
        payload: Dict[str, Any]

    class TurnAnalysisRequest(BaseModel):
        turn_ids: List[str]
        force: bool = False

    class EventFeedbackRequest(BaseModel):
        content: str

    class SendEventFeedbackRequest(BaseModel):
        terminal_session_id: str

    class EventGenerateRequest(BaseModel):
        force: bool = False
        resume: bool = True

    app = FastAPI(title="AgentVAST local Web terminal", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    manager = TerminalManager(
        default_project.resolve(),
        default_claude_command,
        plugin_dir.resolve(),
    )
    app.state.terminal_manager = manager
    feedback_send_lock = asyncio.Lock()
    live_service = LiveTraceService()
    app.state.live_trace_service = live_service

    @app.on_event("startup")
    async def start_live_trace() -> None:
        live_service.start()

    review_tasks: Dict[str, asyncio.Task] = {}
    semantic_tasks: Dict[str, asyncio.Task] = {}
    semantic_progress: Dict[str, Dict[str, Any]] = {}
    event_tasks: Dict[str, asyncio.Task] = {}
    swimlane_tasks: Dict[str, asyncio.Task] = {}
    swimlane_states: Dict[str, Dict[str, Any]] = {}
    event_progress: Dict[str, Dict[str, Any]] = {}

    def persisted_semantic_progress(session_id: str) -> Optional[Dict[str, Any]]:
        stages_root = session_directory(session_id) / "derived" / "semantic_stages"
        if not stages_root.is_dir():
            return None
        state_paths = sorted(
            stages_root.glob("semantic-*/inference_state.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for state_path in state_paths:
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(state, dict) or state.get("status") not in {
                "partial",
                "failed",
                "running",
                "retrying",
                "completed",
            }:
                continue
            status = str(state.get("status"))
            if status == "completed":
                status = "ready"
            if status in {"running", "retrying"}:
                # No task exists in this process, so a persisted running state
                # means the previous process was interrupted and is resumable.
                status = "partial"
                state["retryable"] = True
            return {
                **state,
                "session_id": session_id,
                "status": status,
                "current": state.get("current_episode"),
                "total": state.get("episode_count"),
                "message": ("语义工作流已生成" if status == "ready" else "发现可恢复的语义任务" if status == "partial" else "上次语义任务失败"),
            }
        return None

    def store_for_run(run_id: str) -> Tuple[WorkflowStore, Dict[str, Any]]:
        database_paths = []
        if manager.current is not None:
            database_paths.append(manager.current.database_path)
        database_paths.append(workflow_database(manager.default_project))
        seen: Set[Path] = set()
        for database_path in database_paths:
            resolved = database_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            store = WorkflowStore(resolved)
            try:
                return store, store.get_state(run_id)
            except WorkflowError:
                continue
        raise HTTPException(status_code=404, detail="AgentVAST Run does not exist")

    async def schedule_review(
        store: WorkflowStore, run_id: str, force: bool = False
    ) -> Dict[str, Any]:
        from agentvast.reviewer import review_status
        from agentvast.reviewer.pipeline import reviewer_is_configured

        state = store.get_state(run_id)
        if state["run"]["status"] != "completed":
            raise HTTPException(status_code=409, detail="Reviewer can only process a completed Run")
        if not reviewer_is_configured():
            return {
                "status": "not_configured",
                "message": (
                    "Set AGENTVAST_REVIEW_API_BASE_URL and "
                    "AGENTVAST_REVIEW_MODEL to enable automatic Reviewer generation"
                ),
            }
        existing = review_tasks.get(run_id)
        if existing is not None and not existing.done():
            return {"status": "running", "run_id": run_id}

        workflow_path = store.export_run(run_id)
        project_root = Path(state["run"]["project_root"])
        result_root = Path(state["run"]["result_root"])

        async def run_in_background() -> None:
            from agentvast.reviewer import review_run

            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    None,
                    functools.partial(
                        review_run,
                        project_root,
                        workflow_path,
                        force=force,
                    ),
                )
            except Exception:
                # The Reviewer persists its own failed status. It is intentionally
                # non-blocking and must never change the completed workflow.
                pass

        task = asyncio.create_task(run_in_background())
        review_tasks[run_id] = task
        task.add_done_callback(lambda _task: review_tasks.pop(run_id, None))
        current_status = review_status(result_root)
        if current_status.get("status") == "ready" and not force:
            return current_status
        return {"status": "scheduled", "run_id": run_id}

    @app.get("/api/health")
    async def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "api_version": 2,
            "capabilities": [
                "finish_trace",
                "reviewer_assets",
                "observer_trace_readonly",
                "observer_artifact_open",
                "semantic_workflow_review",
                "passive_observer_terminal",
                "terminal_size_ownership",
                "event_feedback",
                "live_turn_trace",
                "manual_turn_analysis",
            ],
            "default_project": str(manager.default_project),
            "default_claude_command": manager.default_claude_command,
            "plugin_dir": str(manager.plugin_dir),
            "platform": sys.platform,
        }

    @app.get("/api/terminal")
    async def terminal_status() -> Dict[str, Any]:
        if manager.current is None:
            return {"session": None}
        return {"session": manager.current.status()}

    @app.get("/api/observations")
    async def observations() -> Dict[str, Any]:
        return {"sessions": list_observer_sessions()}

    @app.get("/api/observations/{session_id}/trace")
    async def observation_trace(session_id: str) -> Dict[str, Any]:
        try:
            trace = load_observer_trace(session_id)
            state = live_state(session_id)
            if state.get("enabled"):
                trace["live"] = state
                trace["session"]["ended_at"] = read_manifest(session_id).get("ended_at")
            return trace
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    async def feedback_target(session_id: str) -> Dict[str, Any]:
        session = manager.current
        result = {"can_send": False, "terminal_session_id": None, "reason": "请先在 Claude 运行页恢复此会话"}
        if session is None or not session.is_alive():
            return result
        if session.observer_session_id != session_id or session.claude_session_id != session_id:
            result["reason"] = "当前 Claude 正在运行另一个会话，请先恢复此 Event 所属会话"
            return result
        result["terminal_session_id"] = session.session_id
        try:
            if read_manifest(session_id, session.observer_root).get("live_trace_enabled"):
                await asyncio.to_thread(sync_live_trace, session_id, session.observer_root)
            turns = live_state(session_id, session.observer_root).get("turns", [])
            if turns:
                idle = turns[-1].get("execution_state") in {"completed", "interrupted", "failed"}
            else:
                recorded = load_observer_trace(session_id, str(session.observer_root)).get("turns", [])
                idle = bool(recorded and recorded[-1].get("status") == "complete")
        except (OSError, ValueError, RuntimeError):
            result["reason"] = "暂时无法确认 Agent 执行状态，请稍后重试"
            return result
        if not idle:
            result["reason"] = "Agent 正在执行或收尾，意见已保留，请本轮结束后发送"
        elif session.input_pending:
            result["reason"] = "Claude 终端有未提交输入，请先提交或用 Ctrl+U 清空"
        else:
            result.update(can_send=True, reason="将作为新一轮用户消息发送给此 Claude 会话")
        return result

    @app.post("/api/observations/{session_id}/events/{event_id}/feedback")
    async def prepare_event_feedback(session_id: str, event_id: str, request: EventFeedbackRequest) -> Dict[str, Any]:
        try:
            trace = load_observer_trace(session_id)
            try:
                workflow = live_event_workflow(session_id)
                if workflow is None:
                    path = session_directory(session_id) / "derived/event_workflow.json"
                    workflow = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
            except (OSError, ValueError, KeyError):
                workflow = None
            value = build_feedback(trace, event_id, request.content, workflow)
            save_feedback(value)
        except (FileNotFoundError, LookupError) as error:
            raise HTTPException(status_code=404, detail=str(error))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"feedback": value, "delivery": await feedback_target(session_id)}

    @app.get("/api/observations/{session_id}/event-feedback/{feedback_id}")
    async def get_event_feedback(session_id: str, feedback_id: str) -> Dict[str, Any]:
        try:
            value = read_feedback(session_id, feedback_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error))
        return {"feedback": value, "delivery": await feedback_target(session_id)}

    @app.post("/api/observations/{session_id}/event-feedback/{feedback_id}/send")
    async def send_event_feedback(session_id: str, feedback_id: str, request: SendEventFeedbackRequest) -> Dict[str, Any]:
        async with feedback_send_lock:
            try:
                value = read_feedback(session_id, feedback_id)
            except (FileNotFoundError, ValueError) as error:
                raise HTTPException(status_code=404, detail=str(error))
            if value["status"] == "submitted":
                return {"feedback": value, "already_submitted": True}
            if value["status"] != "draft":
                raise HTTPException(status_code=409, detail="此前投递状态未确认，请先检查 Claude 终端，避免重复发送")
            delivery = await feedback_target(session_id)
            session = manager.current
            if not delivery["can_send"]:
                raise HTTPException(status_code=409, detail=delivery["reason"])
            if session is None or request.terminal_session_id != session.session_id:
                raise HTTPException(status_code=409, detail="Claude 终端连接已变化，请刷新预览后重试")
            try:
                value = claim_feedback(session_id, feedback_id, session.session_id)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error))
            try:
                await session.submit_prompt(value["prompt"])
            except Exception as error:
                value.update(status="delivery_uncertain", error=str(error))
                save_feedback(value)
                raise HTTPException(status_code=409, detail="投递未确认，请先检查 Claude 终端，避免重复提交：" + str(error))
            value.update(status="submitted", submitted_at=utc_now())
            save_feedback(value)
            return {"feedback": value, "already_submitted": False}

    @app.get("/api/observations/{session_id}/live")
    async def observation_live_state(session_id: str) -> Dict[str, Any]:
        try:
            return live_state(session_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.get("/api/observations/{session_id}/live/event-workflow")
    async def observation_live_workflow(session_id: str) -> Any:
        try:
            return await asyncio.to_thread(live_event_workflow, session_id)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error))

    @app.post("/api/observations/{session_id}/live/analyze")
    async def analyze_observation_turns(session_id: str, request: TurnAnalysisRequest) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(request_turn_analysis,session_id,request.turn_ids,None,request.force)
        except (FileNotFoundError,ValueError) as error:
            raise HTTPException(status_code=400,detail=str(error))

    @app.post("/api/observations/{session_id}/live/retry")
    async def retry_observation_live(session_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(retry_live_turns, session_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/observations/{session_id}/transcript")
    async def observation_transcript(session_id: str) -> Any:
        try:
            path = session_directory(session_id) / "transcript" / "transcript.jsonl"
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="尚未保存原始 Transcript，请先结束并派生会话记录")
        return FileResponse(
            str(path),
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/observations/{session_id}/artifacts/{artifact_id}")
    async def observation_artifact(session_id: str, artifact_id: str) -> Any:
        try:
            trace = load_observer_trace(session_id)
            path = _resolve_observer_artifact_file(trace, artifact_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=403, detail=str(error))
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers = {"Cache-Control": "no-store"}
        if path.suffix.lower() in {".html", ".htm", ".svg"}:
            headers["Content-Security-Policy"] = (
                "sandbox allow-scripts; default-src 'self' data: blob:; "
                "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:"
            )
        return FileResponse(str(path), media_type=media_type, headers=headers)

    @app.post("/api/observations/{session_id}/artifacts/{artifact_id}/open")
    async def open_observation_artifact(session_id: str, artifact_id: str) -> Dict[str, Any]:
        try:
            trace = load_observer_trace(session_id)
            path = _resolve_observer_artifact_file(trace, artifact_id)
            _open_local_file(path)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error))
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=403, detail=str(error))
        except OSError as error:
            raise HTTPException(
                status_code=500, detail="无法使用本地应用打开文件：{0}".format(error)
            )
        return {"opened": True, "artifact_id": artifact_id}

    @app.get("/api/observations/{session_id}/event-workflow")
    async def observation_event_workflow(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.event_workflow import load_event_workflow

        try:
            return load_event_workflow(session_id)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.get("/api/observations/{session_id}/event-workflow/progress")
    async def observation_event_progress(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.event_workflow import event_workflow_progress

        if session_id in event_progress:
            return event_progress[session_id]
        try:
            return event_workflow_progress(session_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.post("/api/observations/{session_id}/event-workflow/generate")
    async def generate_event_workflow(session_id: str, request: EventGenerateRequest) -> Dict[str, Any]:
        from agentvast.semantic.event_workflow import run_event_workflow, event_workflow_progress
        from agentvast.semantic.provider import SemanticConfig

        if session_id in event_tasks and not event_tasks[session_id].done():
            return dict(event_progress[session_id])
        external = event_workflow_progress(session_id)
        if external.get("status") in {"running", "scheduled"}:
            event_progress.pop(session_id, None)
            return external
        try:
            load_observer_trace(session_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error))
        config = SemanticConfig.from_env()
        if not config.configured():
            raise HTTPException(status_code=400, detail="请先配置语义 API")
        event_progress[session_id] = {
            "session_id": session_id, "status": "scheduled", "stage": "scheduled", "percent": 0,
            "model": config.model, "reasoning_effort": config.reasoning_effort,
            "message": "等待 Event 分析", "error": None,
        }

        def report_event(event: Dict[str, Any]) -> None:
            event_progress[session_id].update(event)

        async def run_event_background() -> None:
            try:
                workflow = await asyncio.get_running_loop().run_in_executor(
                    None, functools.partial(run_event_workflow, session_id, force=request.force,
                                            resume=request.resume, progress_callback=report_event),
                )
                event_progress[session_id].update(workflow["inference_run"])
                event_progress[session_id].update(status="ready", percent=100, message="Event AI 工作流已生成", error=None)
            except Exception as error:
                event_progress[session_id].update(status="partial", error=str(error), message="处理未完成，可继续分析")

        task = asyncio.create_task(run_event_background())
        event_tasks[session_id] = task
        task.add_done_callback(lambda _: event_tasks.pop(session_id, None))
        return dict(event_progress[session_id])

    @app.get("/api/observations/{session_id}/semantic")
    async def observation_semantic_workflow(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.pipeline import load_semantic_workflow

        try:
            return load_semantic_workflow(session_id)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.get("/api/observations/{session_id}/semantic/swimlanes")
    async def observation_swimlanes(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.swimlanes import load_swimlanes
        try:
            return load_swimlanes(session_id)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.get("/api/observations/{session_id}/semantic/swimlanes/progress")
    async def observation_swimlane_progress(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.swimlanes import swimlane_progress
        try:
            if session_id in swimlane_states:
                return swimlane_states[session_id]
            return swimlane_progress(session_id)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.post("/api/observations/{session_id}/semantic/swimlanes/generate")
    async def generate_observation_swimlanes(session_id: str, request: EventGenerateRequest) -> Dict[str, Any]:
        from agentvast.semantic.swimlanes import run_swimlanes, swimlane_progress
        from agentvast.semantic.pipeline import load_semantic_workflow
        from agentvast.semantic.provider import SemanticConfig
        if session_id in swimlane_tasks and not swimlane_tasks[session_id].done():
            return swimlane_states[session_id]
        external = swimlane_progress(session_id)
        if external.get("status") in {"running", "scheduled"}:
            return external
        if session_id in semantic_tasks and not semantic_tasks[session_id].done():
            raise HTTPException(status_code=409, detail="请等待原阶段生成完成再聚合")
        try:
            load_semantic_workflow(session_id)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=404, detail=str(error))
        config = SemanticConfig.from_env()
        if not config.configured():
            raise HTTPException(status_code=400, detail="请先配置语义 API")
        swimlane_states[session_id] = {"status": "scheduled", "message": "等待四泳道语义聚合", "model": config.model,
                                       "reasoning_effort": config.reasoning_effort}

        def report_swimlane(state: Dict[str, Any]) -> None:
            swimlane_states[session_id].update(state)

        async def aggregate_in_background() -> None:
            try:
                result = await asyncio.get_running_loop().run_in_executor(
                    None, functools.partial(run_swimlanes, session_id, force=request.force, progress_callback=report_swimlane)
                )
                swimlane_states[session_id].update(status="ready", message="四泳道语义聚合已完成", **result["inference_run"])
            except Exception as error:
                swimlane_states[session_id].update(status="partial", message="聚合未完成，可重试", error=str(error))

        task = asyncio.create_task(aggregate_in_background())
        swimlane_tasks[session_id] = task
        task.add_done_callback(lambda _: swimlane_tasks.pop(session_id, None))
        return dict(swimlane_states[session_id])

    @app.post("/api/observations/{session_id}/semantic/generate")
    async def generate_observation_semantic_workflow(
        session_id: str, request: SemanticGenerateRequest
    ) -> Dict[str, Any]:
        from agentvast.semantic.pipeline import run_semantic_workflow

        existing = semantic_tasks.get(session_id)
        if existing is not None and not existing.done():
            return semantic_progress[session_id]

        semantic_progress[session_id] = {
            "session_id": session_id,
            "status": "scheduled",
            "stage": "scheduled",
            "percent": 0,
            "message": "等待语义处理",
            "current": None,
            "total": None,
            "error": None,
            "inference_id": None,
            "annotation_guidance": request.annotation_guidance,
        }

        def report_progress(event: Dict[str, Any]) -> None:
            semantic_progress[session_id].update(event)
            semantic_progress[session_id]["status"] = "running"

        async def run_in_background() -> None:
            loop = asyncio.get_running_loop()
            try:
                workflow = await loop.run_in_executor(
                    None,
                    functools.partial(
                        run_semantic_workflow,
                        session_id,
                        rules_only=request.rules_only,
                        force=request.force,
                        resume_inference=request.resume_inference,
                        annotation_guidance=request.annotation_guidance,
                        progress_callback=report_progress,
                    ),
                )
                semantic_progress[session_id].update(
                    {
                        **workflow["inference_run"],
                        "status": "ready",
                        "stage": "complete",
                        "percent": 100,
                        "message": "Semantic Workflow 已生成",
                        "inference_id": workflow["inference_run"]["inference_id"],
                        "error": None,
                    }
                )
            except Exception as error:
                partial_state = getattr(error, "state", None)
                if isinstance(partial_state, dict):
                    semantic_progress[session_id].update(partial_state)
                semantic_progress[session_id].update(
                    {
                        "status": (
                            "partial"
                            if isinstance(partial_state, dict) and partial_state.get("retryable")
                            else "failed"
                        ),
                        "message": (
                            "语义处理已暂停，可从检查点继续"
                            if isinstance(partial_state, dict) and partial_state.get("retryable")
                            else "语义处理失败"
                        ),
                        "error": str(error),
                        "inference_id": (
                            partial_state.get("inference_id")
                            if isinstance(partial_state, dict)
                            else semantic_progress[session_id].get("inference_id")
                        ),
                    }
                )

        task = asyncio.create_task(run_in_background())
        semantic_tasks[session_id] = task
        task.add_done_callback(lambda _task: semantic_tasks.pop(session_id, None))
        return semantic_progress[session_id]

    @app.get("/api/observations/{session_id}/semantic/progress")
    async def observation_semantic_progress(session_id: str) -> Dict[str, Any]:
        from agentvast.semantic.provider import SemanticConfig

        current = semantic_progress.get(session_id)
        if current is not None:
            return current
        persisted = persisted_semantic_progress(session_id)
        if persisted is not None:
            return persisted
        config = SemanticConfig.from_env()
        return {
            "session_id": session_id,
            "status": "idle",
            "stage": "idle",
            "percent": 0,
            "message": "没有正在运行的语义任务",
            "current": None,
            "total": None,
            "error": None,
            "inference_id": None,
            "model": config.model,
            "annotation_concurrency": config.annotation_concurrency,
        }

    @app.post("/api/observations/{session_id}/semantic/reviews")
    async def review_observation_semantic_workflow(
        session_id: str, request: SemanticReviewRequest
    ) -> Dict[str, Any]:
        from agentvast.semantic.review import record_semantic_review

        try:
            return record_semantic_review(session_id, request.action, request.payload)
        except (FileNotFoundError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/terminal")
    async def start_terminal(request: StartTerminalRequest) -> Dict[str, Any]:
        try:
            session = await manager.create(
                project_root=request.project_root,
                rows=request.rows,
                cols=request.cols,
                claude_command=request.claude_command,
                full_permissions=request.full_permissions,
                resume_claude_session_id=request.resume_claude_session_id,
                fresh_run_id=request.fresh_run_id,
            )
        except (FileNotFoundError, ValueError, WebDependencyError) as error:
            raise HTTPException(status_code=400, detail=str(error))
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error))
        return {"session": session.status()}

    def current_session() -> TerminalSession:
        if manager.current is None:
            raise HTTPException(status_code=409, detail="Start Claude before recording")
        return manager.current

    def bound_run(session: TerminalSession, run_id: Optional[str] = None) -> Dict[str, Any]:
        store = WorkflowStore(session.database_path)
        active = store.active_run_for_session(session.claude_session_id)
        if active is None:
            raise HTTPException(
                status_code=404,
                detail="This Claude session has no active AgentVAST Run",
            )
        if run_id is not None and active["run_id"] != run_id:
            raise HTTPException(status_code=409, detail="Run is not bound to this Claude session")
        return active

    @app.get("/api/runs/current")
    async def current_run() -> Dict[str, Any]:
        if manager.current is None:
            store = WorkflowStore(workflow_database(manager.default_project))
            active = store.latest_active_bound_run()
            if active is None:
                return {"run": None, "state": None, "recovery": False}
            return {
                "run": active,
                "state": store.get_state(active["run_id"]),
                "recovery": True,
            }
        session = manager.current
        store = WorkflowStore(session.database_path)
        active = store.active_run_for_session(session.claude_session_id)
        if active is None:
            latest = store.latest_run_for_session(session.claude_session_id)
            if latest is None:
                return {"run": None, "state": None, "recovery": False}
            return {
                "run": latest,
                "state": store.get_state(latest["run_id"]),
                "recovery": False,
            }
        return {
            "run": active,
            "state": store.get_state(active["run_id"]),
            "recovery": False,
        }

    @app.post("/api/runs")
    async def start_run(request: StartRunRequest) -> Dict[str, Any]:
        session = current_session()
        if not session.is_alive():
            raise HTTPException(status_code=409, detail="Claude process is not running")
        store = WorkflowStore(session.database_path)
        existing = store.active_run_for_session(session.claude_session_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="This Claude session already has an active Run: {0}".format(
                    existing["run_id"]
                ),
            )
        try:
            result = store.start_run(
                task_description=request.task,
                original_request=request.task,
                project_root=session.project_root,
                input_files=request.input_files or [],
                claude_session_id=session.claude_session_id,
                checkpoint_mode=request.checkpoint_mode,
            )
            store.bind_session(
                result["run_id"],
                session.claude_session_id,
                session.session_id,
            )
            await _send_control_message(
                session,
                store,
                result["run_id"],
                "activate_run",
                {"instruction": _activation_prompt(result, request.task)},
            )
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"result": result, "state": store.get_state(result["run_id"])}

    @app.post("/api/runs/{run_id}/new-task-trace")
    async def new_task_trace(run_id: str, request: StartRunRequest) -> Dict[str, Any]:
        """Seal the idle current trace and start a new one in the same Claude session."""

        session = current_session()
        bound_run(session, run_id)
        store = WorkflowStore(session.database_path)
        if not request.task.strip():
            raise HTTPException(status_code=400, detail="新任务不能为空")
        # Validate new external paths before closing the current recoverable Run.
        for raw_path in request.input_files or []:
            path = Path(raw_path)
            if not path.is_absolute():
                path = session.project_root / path
            if not path.resolve().is_file():
                raise HTTPException(
                    status_code=400,
                    detail="输入文件不存在：{0}".format(path.resolve()),
                )
        try:
            closed = store.finish_run(run_id)
            closed["export_path"] = str(store.export_run(run_id))
            review = await schedule_review(store, run_id)
            result = store.start_run(
                task_description=request.task,
                original_request=request.task,
                project_root=session.project_root,
                input_files=request.input_files or [],
                claude_session_id=session.claude_session_id,
                checkpoint_mode=request.checkpoint_mode,
            )
            store.bind_session(
                result["run_id"],
                session.claude_session_id,
                session.session_id,
            )
            await _send_control_message(
                session,
                store,
                result["run_id"],
                "activate_new_task_trace",
                {"instruction": _activation_prompt(result, request.task)},
            )
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {
            "closed_run": closed,
            "review": review,
            "result": result,
            "state": store.get_state(result["run_id"]),
        }

    @app.post("/api/runs/{run_id}/approve-plan")
    async def approve_plan(run_id: str, request: PlanApprovalRequest) -> Dict[str, Any]:
        session = current_session()
        bound_run(session, run_id)
        store = WorkflowStore(session.database_path)
        state = store.get_state(run_id)
        if not state["run"]["awaiting_user"] or state["run"]["checkpoint_kind"] != "plan":
            raise HTTPException(
                status_code=409,
                detail="The Run is not waiting for Plan Revision approval",
            )
        event = store.capture_user_input(
            run_id,
            request.note,
            claude_session_id=session.claude_session_id,
        )
        store.classify_user_input(
            event["input_event_id"],
            "checkpoint_continue",
            structured_summary="Plan approved through AgentVAST Web",
        )
        updated = store.get_state(run_id)
        plan_version = updated["plan"]["version"] if updated["plan"] else None
        await _send_control_message(
            session,
            store,
            run_id,
            "plan_approved",
            {
                "input_event_id": event["input_event_id"],
                "plan_version": plan_version,
                "instruction": (
                    "The user approved the current Plan Revision in the AgentVAST "
                    "Web UI. First print the complete approved Plan with the stable "
                    "Node IDs, Chinese objectives, dependencies, and artifact types "
                    "exactly as stored, then continue automatically in this same "
                    "turn: finish an already active Node "
                    "or start the first dependency-ready pending Node, perform the "
                    "real analysis, and complete it truthfully. If findings require "
                    "another Plan Revision, create it, print the complete Revision, "
                    "and stop for Web editing or approval again. After all current Plan "
                    "Nodes are complete, end the turn but keep the Run active for "
                    "follow-up analysis; do not call finish-run automatically."
                ),
            },
        )
        return {"state": updated}

    @app.put("/api/runs/{run_id}/plan")
    async def revise_plan(run_id: str, request: PlanRevisionRequest) -> Dict[str, Any]:
        session = current_session()
        bound_run(session, run_id)
        store = WorkflowStore(session.database_path)
        reason = request.change_reason.strip() or "用户在 AgentVAST Web 修改了后续 Plan"
        try:
            result = store.set_plan(
                run_id,
                request.nodes,
                trigger="human_intervention",
                change_reason=reason,
                replace_plan_checkpoint=True,
            )
            event = store.record_applied_user_input(
                run_id,
                "用户在 AgentVAST Web 中编辑了 Plan：{0}".format(reason),
                "planning_input",
                "创建 Plan Revision {0}；只改变未来 pending Nodes。".format(result["plan_version"]),
                claude_session_id=session.claude_session_id,
                target_plan_version=result["plan_version"],
            )
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {
            "result": result,
            "event": event,
            "state": store.get_state(run_id),
        }

    @app.post("/api/runs/{run_id}/interventions")
    async def add_intervention(run_id: str, request: InterventionRequest) -> Dict[str, Any]:
        session = current_session()
        bound_run(session, run_id)
        if request.input_type not in {
            "analysis_guidance",
            "planning_input",
            "challenge",
        }:
            raise HTTPException(
                status_code=400,
                detail="input_type must be analysis_guidance, planning_input, or challenge",
            )
        store = WorkflowStore(session.database_path)
        try:
            event = store.capture_user_input(
                run_id,
                request.content,
                claude_session_id=session.claude_session_id,
            )
            classified = store.classify_user_input(
                event["input_event_id"],
                request.input_type,
                structured_summary=request.content,
            )
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        await _send_control_message(
            session,
            store,
            run_id,
            "human_intervention",
            {
                "input_event_id": event["input_event_id"],
                "input_type": request.input_type,
                "content": request.content,
                "instruction": (
                    (
                        "This Web input explicitly requests additional analysis or "
                        "a new version of the current Plan or a future-Plan adjustment. "
                        "Treat the user's text as planning feedback, not as permission "
                        "to execute the current Plan. Before material work, create a new "
                        "Plan Revision that retains every active/completed Node "
                        "definition and adds or changes only pending Nodes. Then "
                        "print the complete Revision and stop for Web editing or "
                        "approval before executing its pending Nodes. "
                        if request.input_type == "planning_input"
                        else "Handle this intervention before further material analysis. "
                        "If it changes the analysis path, revise future pending Plan "
                        "Nodes first. "
                    )
                    + "Then record the concrete handling decision with: python -m "
                    "agentvast.agent_cli apply-user-input {0} "
                    '"REAL_WORKFLOW_EFFECT".'
                ).format(event["input_event_id"]),
            },
        )
        return {"event": classified, "state": store.get_state(run_id)}

    @app.post("/api/runs/{run_id}/finish")
    async def finish_trace(run_id: str) -> Dict[str, Any]:
        """Seal an idle successful Trace without submitting another Claude turn."""

        if manager.current is None:
            store = WorkflowStore(workflow_database(manager.default_project))
            active = store.latest_active_bound_run()
            if active is None:
                raise HTTPException(status_code=404, detail="No active Trace to finish")
            if active["run_id"] != run_id:
                raise HTTPException(
                    status_code=409,
                    detail="Requested Trace is not the current recoverable Trace",
                )
        else:
            session = manager.current
            bound_run(session, run_id)
            store = WorkflowStore(session.database_path)
        try:
            result = store.finish_run(run_id)
            result["export_path"] = str(store.export_run(run_id))
            review = await schedule_review(store, run_id)
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {
            "result": result,
            "state": store.get_state(run_id),
            "review": review,
        }

    @app.get("/api/runs/{run_id}/review")
    async def get_review_status(run_id: str) -> Dict[str, Any]:
        from agentvast.reviewer import review_status

        _, state = store_for_run(run_id)
        return review_status(Path(state["run"]["result_root"]))

    @app.get("/api/runs/{run_id}/review/assets")
    async def get_review_assets(run_id: str) -> Dict[str, Any]:
        from agentvast.reviewer import load_review_bundle

        _, state = store_for_run(run_id)
        try:
            return load_review_bundle(Path(state["run"]["result_root"]))
        except RuntimeError as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.post("/api/runs/{run_id}/review")
    async def start_review(run_id: str, request: ReviewRequest) -> Dict[str, Any]:
        store, _ = store_for_run(run_id)
        return await schedule_review(store, run_id, force=request.force)

    @app.post("/api/runs/{run_id}/abort")
    async def abort_run(run_id: str, request: AbortRunRequest) -> Dict[str, Any]:
        session = current_session()
        bound_run(session, run_id)
        store = WorkflowStore(session.database_path)
        try:
            result = store.abort_run(run_id, request.reason)
            result["export_path"] = str(store.export_run(run_id))
        except WorkflowError as error:
            raise HTTPException(status_code=400, detail=str(error))
        await session.interrupt()
        return {"result": result, "state": store.get_state(run_id)}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str) -> Any:
        session = current_session()
        bound_run(session, run_id)
        store = WorkflowStore(session.database_path)

        async def stream() -> Any:
            previous = ""
            while True:
                try:
                    state = store.get_state(run_id)
                except WorkflowError as error:
                    yield "event: error\ndata: {0}\n\n".format(
                        json.dumps({"message": str(error)}, ensure_ascii=False)
                    )
                    return
                encoded = json.dumps(state, ensure_ascii=False, sort_keys=True)
                if encoded != previous:
                    previous = encoded
                    yield "event: workflow\ndata: {0}\n\n".format(encoded)
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.delete("/api/terminal/{session_id}")
    async def close_terminal(session_id: str) -> Dict[str, Any]:
        try:
            session = manager.get(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error))
        await session.close()
        return {"session": session.status()}

    @app.websocket("/ws/terminal/{session_id}")
    async def terminal_socket(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        try:
            session = manager.get(session_id)
        except KeyError as error:
            await websocket.send_json({"type": "error", "message": str(error)})
            await websocket.close(code=4404)
            return

        queue, replay = session.subscribe()
        if replay:
            await websocket.send_json({"type": "output", "data": replay, "replay": True})
        await websocket.send_json({"type": "status", **session.status()})

        async def send_messages() -> None:
            while True:
                await websocket.send_json(await queue.get())

        sender = asyncio.create_task(send_messages())
        try:
            while True:
                message = await websocket.receive_json()
                message_type = message.get("type")
                if message_type == "input":
                    await session.claim_size(queue)
                    await session.write(str(message.get("data", "")))
                elif message_type == "resize":
                    await session.resize(
                        int(message.get("rows", 24)),
                        int(message.get("cols", 80)),
                        client=queue,
                    )
                elif message_type == "activate":
                    await session.claim_size(queue)
                elif message_type == "deactivate":
                    session.release_size(queue)
                elif message_type == "interrupt":
                    await session.claim_size(queue)
                    await session.interrupt()
                elif message_type == "close":
                    await session.close()
                else:
                    await websocket.send_json(
                        {"type": "error", "message": "Unknown terminal message"}
                    )
        except WebSocketDisconnect:
            pass
        except Exception as error:
            try:
                await websocket.send_json({"type": "error", "message": str(error)})
            except Exception:
                pass
        finally:
            sender.cancel()
            session.unsubscribe(queue)

    @app.on_event("shutdown")
    async def close_process_on_shutdown() -> None:
        await manager.shutdown()
        await live_service.close()

    return app
