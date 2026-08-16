from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import BinaryIO
import uuid

from .config import CommandConfig, ExecutionConfig
from .models import CommandResult

_MAX_OUTPUT_BYTES = 24_000
_TERMINATE_GRACE_SECONDS = 1.0

_PRESERVED_ENVIRONMENT = {
    "PATH",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "CI",
    "SYSTEMROOT",
    "WINDIR",
    "PATHEXT",
    "COMSPEC",
}

_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|token|secret|password|passwd|credential)\s*[=:]\s*)[^\s,;&#]+"
    ),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@"),
    re.compile(
        r"(?i)([?&](?:access_token|api[_-]?key|auth|credential|password|secret|token)=)[^\s&#]+"
    ),
    re.compile(
        r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


class ExecutionUnavailable(RuntimeError):
    """Raised when the requested command boundary cannot be provided safely."""


@dataclass(frozen=True, slots=True)
class ExecutorSelection:
    mode: str
    runtime_name: str = ""
    runtime_path: str = ""
    container_image: str = ""
    network: bool = False
    memory_mb: int = 0
    cpus: float = 0.0
    pids_limit: int = 0
    tmpfs_mb: int = 0

    @property
    def label(self) -> str:
        if self.mode == "container":
            return f"container:{self.runtime_name}"
        return self.mode


def select_executor(config: ExecutionConfig) -> ExecutorSelection:
    """Resolve one explicit command-execution boundary.

    Auto mode never falls back to native execution unless the trusted policy
    explicitly opts into the weak native boundary.
    """

    if config.mode == "static":
        return ExecutorSelection(mode="static")
    if config.mode == "native":
        if not config.allow_unsafe_native:
            raise ExecutionUnavailable(
                "native execution requires execution.allow_unsafe_native = true"
            )
        return ExecutorSelection(mode="native", network=True)

    if not sys_platform_linux():
        if config.mode == "container":
            raise ExecutionUnavailable(
                "container execution is currently supported only on Linux hosts"
            )
        if config.allow_unsafe_native:
            return ExecutorSelection(mode="native", network=True)
        raise ExecutionUnavailable(
            "auto mode cannot provide isolated container execution on this host"
        )

    runtime_name, runtime_path = _find_container_runtime(config.container_runtime)
    if runtime_path and config.container_image:
        return ExecutorSelection(
            mode="container",
            runtime_name=runtime_name,
            runtime_path=runtime_path,
            container_image=config.container_image,
            network=config.network,
            memory_mb=config.memory_mb,
            cpus=config.cpus,
            pids_limit=config.pids_limit,
            tmpfs_mb=config.tmpfs_mb,
        )

    if config.mode == "container":
        if not config.container_image:
            raise ExecutionUnavailable("container mode requires a digest-pinned image")
        raise ExecutionUnavailable(
            f"container runtime {config.container_runtime!r} is not available"
        )

    if config.allow_unsafe_native:
        return ExecutorSelection(mode="native", network=True)
    if not config.container_image:
        raise ExecutionUnavailable(
            "auto mode has no digest-pinned container image and unsafe native execution is disabled"
        )
    raise ExecutionUnavailable(
        f"no supported container runtime is available for {config.container_image}"
    )


def sanitized_environment(
    allow_env: tuple[str, ...] = (),
    *,
    sandbox_home: Path | None = None,
    sandbox_tmp: Path | None = None,
) -> dict[str, str]:
    """Return a small environment without inherited credentials."""

    allowed = set(allow_env)
    result: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in allowed or key in _PRESERVED_ENVIRONMENT:
            result[key] = value

    if "HOME" not in allowed and sandbox_home is not None:
        result["HOME"] = os.fspath(sandbox_home)
        result["XDG_CONFIG_HOME"] = os.fspath(sandbox_home / ".config")
        result["XDG_CACHE_HOME"] = os.fspath(sandbox_home / ".cache")
        result["PIP_CONFIG_FILE"] = os.devnull
        result["GIT_CONFIG_NOSYSTEM"] = "1"
        result["GIT_CONFIG_GLOBAL"] = os.devnull
        result["NPM_CONFIG_USERCONFIG"] = os.fspath(sandbox_home / ".npmrc")
    elif "HOME" in allowed and "HOME" in os.environ:
        result["HOME"] = os.environ["HOME"]

    if sandbox_tmp is not None:
        for key in ("TMPDIR", "TEMP", "TMP"):
            if key not in allowed:
                result[key] = os.fspath(sandbox_tmp)

    result["PATCHLAB_SANDBOX"] = "native"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    result["PYTHONSAFEPATH"] = "1"
    return result


def run_command(
    config: CommandConfig,
    phase: str,
    cwd: Path,
    executor: ExecutorSelection | None = None,
) -> CommandResult:
    selected = executor or ExecutorSelection(mode="native")
    if selected.mode == "native":
        return _run_native_command(config, phase, cwd)
    if selected.mode == "container":
        return _run_container_command(config, phase, cwd, selected)
    raise ExecutionUnavailable(f"cannot execute commands with {selected.mode!r} mode")


def _run_native_command(config: CommandConfig, phase: str, cwd: Path) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    exit_code: int | None = None
    launch_error = ""
    stdout_capture = _BoundedCapture()
    stderr_capture = _BoundedCapture()

    with (
        tempfile.TemporaryDirectory(prefix="patchlab-home-") as home_raw,
        tempfile.TemporaryDirectory(prefix="patchlab-tmp-") as tmp_raw,
    ):
        home = Path(home_raw)
        temporary = Path(tmp_raw)
        environment = sanitized_environment(
            config.allow_env,
            sandbox_home=home,
            sandbox_tmp=temporary,
        )
        # Project code must be importable while the parent process remains
        # protected from inherited Python path manipulation. Native execution
        # is an explicitly acknowledged weak boundary, so the candidate root
        # is added only to the child process.
        environment["PYTHONPATH"] = os.fspath(cwd.resolve())
        popen_options: dict[str, object] = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True

        process: subprocess.Popen[bytes] | None = None
        threads: tuple[threading.Thread, threading.Thread] = ()
        try:
            command = _resolve_native_command(config.command, cwd, environment)
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **popen_options,
            )
            threads = _start_capture_threads(process, stdout_capture, stderr_capture)
            try:
                exit_code = process.wait(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                exit_code = process.returncode
            finally:
                if process is not None and os.name != "nt":
                    _terminate_remaining_process_group(process.pid)
        except (OSError, ExecutionUnavailable) as exc:
            launch_error = f"could not start command: {exc}"
        finally:
            if process is not None:
                _finish_capture_threads(process, threads)

    stdout = stdout_capture.render()
    stderr = stderr_capture.render()
    if launch_error:
        stderr = _join_output(stderr, launch_error)
    if timed_out:
        stderr = _join_output(
            stderr,
            f"PatchLab terminated the command tree after {config.timeout_seconds} seconds.",
        )

    return _command_result(
        config,
        phase,
        exit_code,
        timed_out,
        time.monotonic() - started,
        stdout,
        stderr,
        executor="native",
        network_enabled=True,
    )

def _run_container_command(
    config: CommandConfig,
    phase: str,
    cwd: Path,
    executor: ExecutorSelection,
) -> CommandResult:
    if os.name == "nt" or not sys_platform_linux():
        raise ExecutionUnavailable("container execution is currently supported only on Linux hosts")

    started = time.monotonic()
    timed_out = False
    exit_code: int | None = None
    launch_error = ""
    name = f"patchlab-{os.getpid()}-{uuid.uuid4().hex[:12]}"
    stdout_capture = _BoundedCapture()
    stderr_capture = _BoundedCapture()

    with tempfile.TemporaryDirectory(prefix="patchlab-runtime-home-") as runtime_home_raw:
        runtime_home = Path(runtime_home_raw)
        runtime_env = _runtime_environment(runtime_home, config.allow_env)
        command = _container_command(executor, cwd, name, config)
        process: subprocess.Popen[bytes] | None = None
        threads: tuple[threading.Thread, threading.Thread] = ()
        try:
            process = subprocess.Popen(
                command,
                cwd=runtime_home,
                env=runtime_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            threads = _start_capture_threads(process, stdout_capture, stderr_capture)
            try:
                exit_code = process.wait(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _remove_container(executor.runtime_path, name, runtime_env)
                _terminate_process_tree(process)
                exit_code = process.returncode
        except OSError as exc:
            launch_error = f"could not start container runtime: {exc}"
        finally:
            _remove_container(executor.runtime_path, name, runtime_env)
            if process is not None:
                _finish_capture_threads(process, threads)

    stdout = stdout_capture.render()
    stderr = stderr_capture.render()
    if launch_error:
        stderr = _join_output(stderr, launch_error)
    if timed_out:
        stderr = _join_output(
            stderr,
            f"PatchLab removed the isolated container after {config.timeout_seconds} seconds.",
        )

    return _command_result(
        config,
        phase,
        exit_code,
        timed_out,
        time.monotonic() - started,
        stdout,
        stderr,
        executor=executor.label,
        network_enabled=executor.network,
    )

def _container_command(
    executor: ExecutorSelection,
    cwd: Path,
    name: str,
    config: CommandConfig,
) -> list[str]:
    workspace = cwd.resolve()
    if not workspace.is_dir():
        raise ExecutionUnavailable(f"snapshot directory does not exist: {workspace}")
    if ":" in os.fspath(workspace):
        raise ExecutionUnavailable("container snapshot path contains an unsupported colon")

    network = "bridge" if executor.network else "none"
    command = [
        executor.runtime_path,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--network",
        network,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--read-only",
        "--ipc=none",
        "--pids-limit",
        str(executor.pids_limit),
        "--memory",
        f"{executor.memory_mb}m",
        "--cpus",
        str(executor.cpus),
        "--ulimit",
        "nofile=1024:1024",
        "--ulimit",
        "core=0:0",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={executor.tmpfs_mb}m,mode=1777",
        "--tmpfs",
        "/run:rw,noexec,nosuid,nodev,size=16m,mode=755",
        "--user",
        "65532:65532",
        "--volume",
        f"{workspace}:/workspace:ro",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/tmp/patchlab-home",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "PATCHLAB_SANDBOX=container",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONNOUSERSITE=1",
        "--env",
        "PYTHONSAFEPATH=1",
        "--env",
        "PYTHONPATH=/workspace",
    ]
    for key in config.allow_env:
        if key in os.environ:
            # Pass only the variable name. The runtime reads its value from its
            # own sanitized environment, so credentials never enter argv.
            command.extend(("--env", key))
    command.append(executor.container_image)
    command.extend(config.command)
    return command

def _find_container_runtime(preference: str) -> tuple[str, str]:
    candidates = (preference,) if preference != "auto" else ("docker", "podman")
    path = os.environ.get("PATH", os.defpath)
    for name in candidates:
        executable = shutil.which(name, path=path)
        if executable:
            return name, os.path.abspath(executable)
    return "", ""


def _runtime_environment(home: Path, allow_env: tuple[str, ...] = ()) -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    for key in allow_env:
        value = os.environ.get(key)
        if value is not None:
            environment[key] = value
    environment.update(
        {
            "HOME": os.fspath(home),
            "DOCKER_CONFIG": os.fspath(home / ".docker"),
            "XDG_CONFIG_HOME": os.fspath(home / ".config"),
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _remove_container(runtime: str, name: str, environment: dict[str, str]) -> None:
    if not runtime:
        return
    try:
        subprocess.run(
            [runtime, "rm", "-f", name],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


class _BoundedCapture:
    """Drain an output stream while retaining only bounded evidence."""

    def __init__(self, limit: int = _MAX_OUTPUT_BYTES) -> None:
        self._limit = limit
        self._head_limit = limit // 2
        self._tail_limit = limit - self._head_limit
        self._head = bytearray()
        self._tail = bytearray()
        self._total = 0
        self._lock = threading.Lock()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self._total += len(chunk)
            remaining_head = self._head_limit - len(self._head)
            if remaining_head > 0:
                self._head.extend(chunk[:remaining_head])
                chunk = chunk[remaining_head:]
            if chunk:
                self._tail.extend(chunk)
                if len(self._tail) > self._tail_limit:
                    del self._tail[: len(self._tail) - self._tail_limit]

    def render(self) -> str:
        with self._lock:
            if self._total <= self._limit:
                raw = bytes(self._head + self._tail)
            else:
                omitted = self._total - len(self._head) - len(self._tail)
                marker = f"\n... PatchLab omitted {omitted} output bytes ...\n".encode()
                raw = bytes(self._head) + marker + bytes(self._tail)
        return raw.decode("utf-8", errors="replace")


def _start_capture_threads(
    process: subprocess.Popen[bytes],
    stdout_capture: _BoundedCapture,
    stderr_capture: _BoundedCapture,
) -> tuple[threading.Thread, threading.Thread]:
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("internal error: subprocess pipes were not created")
    threads = (
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_capture),
            name="patchlab-stdout",
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_capture),
            name="patchlab-stderr",
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    return threads


def _drain_stream(stream: BinaryIO, capture: _BoundedCapture) -> None:
    try:
        while chunk := stream.read(64 * 1024):
            capture.feed(chunk)
    except (OSError, ValueError):
        pass


def _finish_capture_threads(
    process: subprocess.Popen[bytes],
    threads: tuple[threading.Thread, threading.Thread],
) -> None:
    for thread in threads:
        thread.join(timeout=2)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    for thread in threads:
        thread.join(timeout=1)


def _resolve_native_command(
    command: tuple[str, ...], cwd: Path, environment: dict[str, str]
) -> list[str]:
    program = command[0]
    separators = tuple(item for item in (os.sep, os.altsep) if item)
    if os.path.isabs(program):
        executable = Path(program)
    elif any(separator in program for separator in separators):
        executable = (cwd / program).resolve()
        try:
            executable.relative_to(cwd.resolve())
        except ValueError as exc:
            raise ExecutionUnavailable("relative program path escapes the snapshot") from exc
    else:
        resolved = shutil.which(program, path=environment.get("PATH", os.defpath))
        if not resolved:
            raise ExecutionUnavailable(f"program was not found on PATH: {program}")
        executable = Path(resolved).resolve()
    if not executable.is_file():
        raise ExecutionUnavailable(f"program is not a regular file: {executable}")
    return [os.fspath(executable), *command[1:]]


def _command_result(
    config: CommandConfig,
    phase: str,
    exit_code: int | None,
    timed_out: bool,
    duration: float,
    stdout: str,
    stderr: str,
    *,
    executor: str,
    network_enabled: bool,
) -> CommandResult:
    passed = (
        exit_code is not None
        and not timed_out
        and _expected_pass(config.expected_exit, phase, exit_code)
    )
    return CommandResult(
        name=config.name,
        phase=phase,
        command=tuple(_redact_argument(item) for item in config.command),
        required=config.required,
        expected_exit=config.expected_exit,
        exit_code=exit_code,
        passed=passed,
        timed_out=timed_out,
        duration_seconds=round(duration, 3),
        stdout=_redact_output(stdout),
        stderr=_redact_output(stderr),
        executor=executor,
        network_enabled=network_enabled,
    )


def _expected_pass(expected: str, phase: str, exit_code: int) -> bool:
    if expected == "zero":
        return exit_code == 0
    if expected == "nonzero":
        return exit_code != 0
    if expected == "base_nonzero_head_zero":
        return exit_code != 0 if phase == "base" else exit_code == 0
    raise ValueError(f"unknown expected exit policy: {expected}")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        try:
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _terminate_remaining_process_group(group_id: int) -> None:
    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(0.02)
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _redact_output(value: str) -> str:
    redacted = value
    for pattern in _REDACTION_PATTERNS:
        if pattern.groups:
            if pattern.pattern.startswith("(?i)(https?://)"):
                redacted = pattern.sub(lambda match: match.group(1), redacted)
            else:
                redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _redact_argument(value: str) -> str:
    return _redact_output(value)


def _join_output(current: str, addition: str) -> str:
    if not current:
        return addition
    return f"{current.rstrip()}\n{addition}"


def sys_platform_linux() -> bool:
    return os.name == "posix" and os.uname().sysname == "Linux"
