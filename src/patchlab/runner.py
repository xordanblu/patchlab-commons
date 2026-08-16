from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from typing import BinaryIO

from .config import CommandConfig
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
    "VIRTUAL_ENV",
}
_ALLOWED_GITHUB_ENVIRONMENT = {
    "GITHUB_ACTIONS",
    "GITHUB_WORKSPACE",
    "GITHUB_SHA",
    "GITHUB_REF",
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


def sanitized_environment(
    allow_env: tuple[str, ...] = (),
    *,
    sandbox_home: Path | None = None,
    sandbox_tmp: Path | None = None,
) -> dict[str, str]:
    """Return a small environment without inherited credentials.

    Variables listed in ``allow_env`` are copied exactly. All other variables
    are dropped unless PatchLab needs them to start normal local programs.
    """

    allowed = set(allow_env)
    result: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in allowed or key in _PRESERVED_ENVIRONMENT:
            result[key] = value
            continue
        if key in _ALLOWED_GITHUB_ENVIRONMENT:
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

    result["PATCHLAB_SANDBOX"] = "1"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONNOUSERSITE"] = "1"
    return result


def _expected_pass(expected: str, phase: str, exit_code: int) -> bool:
    if expected == "zero":
        return exit_code == 0
    if expected == "nonzero":
        return exit_code != 0
    if expected == "base_nonzero_head_zero":
        return exit_code != 0 if phase == "base" else exit_code == 0
    raise ValueError(f"unknown expected exit policy: {expected}")


def run_command(config: CommandConfig, phase: str, cwd: Path) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    exit_code: int | None = None
    launch_error = ""

    with (
        tempfile.TemporaryDirectory(prefix="patchlab-home-") as home_raw,
        tempfile.TemporaryDirectory(prefix="patchlab-tmp-") as tmp_raw,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        home = Path(home_raw)
        temporary = Path(tmp_raw)
        environment = sanitized_environment(
            config.allow_env,
            sandbox_home=home,
            sandbox_tmp=temporary,
        )
        popen_options: dict[str, object] = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True

        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                list(config.command),
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                **popen_options,
            )
            try:
                exit_code = process.wait(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                exit_code = process.returncode
        except OSError as exc:
            launch_error = f"could not start command: {exc}"

        stdout = _read_bounded(stdout_file)
        stderr = _read_bounded(stderr_file)

    if launch_error:
        stderr = _join_output(stderr, launch_error)
    if timed_out:
        stderr = _join_output(
            stderr,
            f"PatchLab terminated the command tree after {config.timeout_seconds} seconds.",
        )

    duration = time.monotonic() - started
    passed = exit_code is not None and not timed_out and _expected_pass(config.expected_exit, phase, exit_code)
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
    )


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


def _read_bounded(handle: BinaryIO) -> str:
    handle.flush()
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    handle.seek(0)
    if size <= _MAX_OUTPUT_BYTES:
        raw = handle.read()
    else:
        first_size = _MAX_OUTPUT_BYTES // 2
        last_size = _MAX_OUTPUT_BYTES - first_size
        first = handle.read(first_size)
        handle.seek(-last_size, os.SEEK_END)
        last = handle.read(last_size)
        removed = size - len(first) - len(last)
        marker = f"\n... PatchLab omitted {removed} output bytes ...\n".encode("utf-8")
        raw = first + marker + last
    return raw.decode("utf-8", errors="replace")


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
