from __future__ import annotations

import fnmatch
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Disposition

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PINNED_IMAGE_RE = re.compile(r"^(?:[^\s@]+@sha256:[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
_SENSITIVE_ENV_NAME_RE = re.compile(
    r"(?i)(?:^|_)(?:AUTH|COOKIE|CREDENTIAL|KEY|PASS(?:WORD|WD)?|SECRET|TOKEN)(?:_|$)"
)

_TOP_LEVEL_KEYS = {"project", "scope", "policy", "execution", "commands"}
_PROJECT_KEYS = {"name"}
_SCOPE_KEYS = {"allow", "deny", "max_files", "max_added_lines", "max_deleted_lines"}
_POLICY_KEYS = {
    "dependency_changes",
    "workflow_changes",
    "dangerous_permissions",
    "secret_exposure",
    "network_additions",
    "test_weakening",
    "binary_files",
    "generated_files",
    "fail_on_review",
    "require_clean_worktree",
    "require_human_review",
}
_EXECUTION_KEYS = {
    "mode",
    "container_runtime",
    "container_image",
    "network",
    "memory_mb",
    "cpus",
    "pids_limit",
    "tmpfs_mb",
    "allow_unsafe_native",
}
_COMMAND_KEYS = {
    "name",
    "command",
    "run_on",
    "expected_exit",
    "timeout_seconds",
    "required",
    "allow_env",
}


class ConfigError(ValueError):
    """Raised when patchlab.toml is invalid."""


@dataclass(frozen=True, slots=True)
class CommandConfig:
    name: str
    command: tuple[str, ...]
    run_on: str = "head"
    expected_exit: str = "zero"
    timeout_seconds: int = 300
    required: bool = True
    allow_env: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    mode: str = "static"
    container_runtime: str = "auto"
    container_image: str = ""
    network: bool = False
    memory_mb: int = 1024
    cpus: float = 1.0
    pids_limit: int = 128
    tmpfs_mb: int = 64
    allow_unsafe_native: bool = False


@dataclass(frozen=True, slots=True)
class ScopeConfig:
    allow: tuple[str, ...] = ("**",)
    deny: tuple[str, ...] = ()
    max_files: int = 100
    max_added_lines: int = 5000
    max_deleted_lines: int = 5000

    def allowed(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in self.deny):
            return False
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.allow)


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    dependency_changes: Disposition = Disposition.REVIEW
    workflow_changes: Disposition = Disposition.REVIEW
    dangerous_permissions: Disposition = Disposition.DENY
    secret_exposure: Disposition = Disposition.DENY
    network_additions: Disposition = Disposition.REVIEW
    test_weakening: Disposition = Disposition.DENY
    binary_files: Disposition = Disposition.REVIEW
    generated_files: Disposition = Disposition.REVIEW
    fail_on_review: bool = False
    require_clean_worktree: bool = False
    require_human_review: bool = True


@dataclass(frozen=True, slots=True)
class PatchLabConfig:
    project_name: str
    commands: tuple[CommandConfig, ...] = ()
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)


DEFAULT_CONFIG = """# PatchLab Commons configuration

[project]
name = "my-project"

[execution]
# Static mode never executes project code. Use container mode with a digest-pinned
# image when commands must run. Native mode is a weak boundary and requires an
# explicit opt-in.
mode = "static"
container_runtime = "auto"
container_image = ""
network = false
memory_mb = 1024
cpus = 1.0
pids_limit = 128
tmpfs_mb = 64
allow_unsafe_native = false

[scope]
allow = ["src/**", "tests/**", "pyproject.toml", "package.json", ".github/workflows/**"]
deny = ["**/*.pem", "**/*.key", ".env", ".env.*"]
max_files = 100
max_added_lines = 5000
max_deleted_lines = 5000

[policy]
dependency_changes = "review"
workflow_changes = "review"
dangerous_permissions = "deny"
secret_exposure = "deny"
network_additions = "review"
test_weakening = "deny"
binary_files = "review"
generated_files = "review"
fail_on_review = false
require_clean_worktree = false
require_human_review = true

# The reproduction command must fail on the base ref and pass on the head ref.
[[commands]]
name = "reproduction"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 120
required = true

[[commands]]
name = "test-suite"
command = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 300
required = true
"""


def load_config(path: str | Path) -> PatchLabConfig:
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {config_path}") from exc
    return load_config_text(text, source=str(config_path))


def load_config_text(text: str, source: str = "<memory>") -> PatchLabConfig:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {source}: {exc}") from exc

    _reject_unknown_keys(data, _TOP_LEVEL_KEYS, "top level")
    project = _expect_table(data, "project")
    _reject_unknown_keys(project, _PROJECT_KEYS, "[project]")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("[project].name must be a non-empty string")

    scope_data = _expect_table(data, "scope")
    _reject_unknown_keys(scope_data, _SCOPE_KEYS, "[scope]")
    scope = ScopeConfig(
        allow=_as_str_tuple(scope_data.get("allow", ["**"]), "scope.allow"),
        deny=_as_str_tuple(scope_data.get("deny", []), "scope.deny"),
        max_files=_positive_int(scope_data.get("max_files", 100), "scope.max_files"),
        max_added_lines=_positive_int(
            scope_data.get("max_added_lines", 5000),
            "scope.max_added_lines",
        ),
        max_deleted_lines=_positive_int(
            scope_data.get("max_deleted_lines", 5000),
            "scope.max_deleted_lines",
        ),
    )

    execution_data = _expect_table(data, "execution")
    _reject_unknown_keys(execution_data, _EXECUTION_KEYS, "[execution]")
    mode = _choice(
        execution_data.get("mode", "static"),
        "execution.mode",
        {"auto", "static", "container", "native"},
    )
    container_runtime = _choice(
        execution_data.get("container_runtime", "auto"),
        "execution.container_runtime",
        {"auto", "docker", "podman"},
    )
    container_image = execution_data.get("container_image", "")
    if not isinstance(container_image, str):
        raise ConfigError("execution.container_image must be a string")
    container_image = container_image.strip()
    if container_image and not _PINNED_IMAGE_RE.fullmatch(container_image):
        raise ConfigError(
            "execution.container_image must use an immutable @sha256 digest or image ID"
        )
    execution = ExecutionConfig(
        mode=mode,
        container_runtime=container_runtime,
        container_image=container_image,
        network=_boolean(execution_data.get("network", False), "execution.network"),
        memory_mb=_positive_int(
            execution_data.get("memory_mb", 1024), "execution.memory_mb"
        ),
        cpus=_positive_number(execution_data.get("cpus", 1.0), "execution.cpus"),
        pids_limit=_positive_int(
            execution_data.get("pids_limit", 128), "execution.pids_limit"
        ),
        tmpfs_mb=_positive_int(
            execution_data.get("tmpfs_mb", 64), "execution.tmpfs_mb"
        ),
        allow_unsafe_native=_boolean(
            execution_data.get("allow_unsafe_native", False),
            "execution.allow_unsafe_native",
        ),
    )
    if mode == "container" and not container_image:
        raise ConfigError("execution.container_image is required in container mode")
    if mode == "native" and not execution.allow_unsafe_native:
        raise ConfigError(
            "execution.allow_unsafe_native must be true when execution.mode is native"
        )

    policy_data = _expect_table(data, "policy")
    _reject_unknown_keys(policy_data, _POLICY_KEYS, "[policy]")
    policy = PolicyConfig(
        dependency_changes=_disposition(
            policy_data.get("dependency_changes"),
            "policy.dependency_changes",
            Disposition.REVIEW,
        ),
        workflow_changes=_disposition(
            policy_data.get("workflow_changes"),
            "policy.workflow_changes",
            Disposition.REVIEW,
        ),
        dangerous_permissions=_disposition(
            policy_data.get("dangerous_permissions"),
            "policy.dangerous_permissions",
            Disposition.DENY,
        ),
        secret_exposure=_disposition(
            policy_data.get("secret_exposure"),
            "policy.secret_exposure",
            Disposition.DENY,
        ),
        network_additions=_disposition(
            policy_data.get("network_additions"),
            "policy.network_additions",
            Disposition.REVIEW,
        ),
        test_weakening=_disposition(
            policy_data.get("test_weakening"),
            "policy.test_weakening",
            Disposition.DENY,
        ),
        binary_files=_disposition(
            policy_data.get("binary_files"),
            "policy.binary_files",
            Disposition.REVIEW,
        ),
        generated_files=_disposition(
            policy_data.get("generated_files"),
            "policy.generated_files",
            Disposition.REVIEW,
        ),
        fail_on_review=_boolean(
            policy_data.get("fail_on_review", False),
            "policy.fail_on_review",
        ),
        require_clean_worktree=_boolean(
            policy_data.get("require_clean_worktree", False),
            "policy.require_clean_worktree",
        ),
        require_human_review=_boolean(
            policy_data.get("require_human_review", True),
            "policy.require_human_review",
        ),
    )

    command_items = data.get("commands", [])
    if not isinstance(command_items, list):
        raise ConfigError("[[commands]] must be an array of tables")
    commands: list[CommandConfig] = []
    names: set[str] = set()
    for index, item in enumerate(command_items):
        if not isinstance(item, dict):
            raise ConfigError(f"commands[{index}] must be a table")
        _reject_unknown_keys(item, _COMMAND_KEYS, f"commands[{index}]")
        command_name = item.get("name")
        if not isinstance(command_name, str) or not command_name.strip():
            raise ConfigError(f"commands[{index}].name must be a non-empty string")
        command_name = command_name.strip()
        if command_name in names:
            raise ConfigError(f"duplicate command name: {command_name}")
        names.add(command_name)
        command = _command_tuple(item.get("command"), f"commands[{index}].command")
        run_on_value = item.get("run_on", "head")
        if not isinstance(run_on_value, str):
            raise ConfigError(f"commands[{index}].run_on must be a string")
        run_on = run_on_value
        if run_on not in {"base", "head", "both"}:
            raise ConfigError(f"commands[{index}].run_on must be base, head, or both")
        expected_value = item.get("expected_exit", "zero")
        if not isinstance(expected_value, str):
            raise ConfigError(f"commands[{index}].expected_exit must be a string")
        expected = expected_value
        if expected not in {"zero", "nonzero", "base_nonzero_head_zero"}:
            raise ConfigError(
                f"commands[{index}].expected_exit must be zero, nonzero, or base_nonzero_head_zero"
            )
        if expected == "base_nonzero_head_zero" and run_on != "both":
            raise ConfigError(
                f"commands[{index}] must use run_on = 'both' with base_nonzero_head_zero"
            )
        commands.append(
            CommandConfig(
                name=command_name,
                command=command,
                run_on=run_on,
                expected_exit=expected,
                timeout_seconds=_positive_int(
                    item.get("timeout_seconds", 300),
                    f"commands[{index}].timeout_seconds",
                ),
                required=_boolean(item.get("required", True), f"commands[{index}].required"),
                allow_env=_environment_names(
                    item.get("allow_env", []),
                    f"commands[{index}].allow_env",
                ),
            )
        )

    return PatchLabConfig(
        project_name=name.strip(),
        commands=tuple(commands),
        scope=scope,
        policy=policy,
        execution=execution,
    )


def is_pinned_container_image(value: str) -> bool:
    return bool(_PINNED_IMAGE_RE.fullmatch(value))


def _reject_unknown_keys(data: dict[str, Any], allowed: set[str], location: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"unknown key in {location}: {unknown[0]}")


def _expect_table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return value


def _as_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{field_name} must be an array of strings")
    return tuple(value)


def _disposition(value: Any, field_name: str, default: Disposition) -> Disposition:
    raw = default.value if value is None else value
    try:
        return Disposition(str(raw))
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be allow, review, or deny") from exc


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field_name} must be true or false")
    return value


def _command_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    command = _as_str_tuple(value, field_name)
    if not command or not command[0]:
        raise ConfigError(f"{field_name} must contain a non-empty program name")
    if any("\x00" in item for item in command):
        raise ConfigError(f"{field_name} must not contain NUL characters")
    return command


def _environment_names(value: Any, field_name: str) -> tuple[str, ...]:
    names = _as_str_tuple(value, field_name)
    invalid = [name for name in names if not _ENV_NAME_RE.fullmatch(name)]
    if invalid:
        raise ConfigError(f"{field_name} contains an invalid environment variable name: {invalid[0]!r}")
    if len(names) != len(set(names)):
        raise ConfigError(f"{field_name} must not contain duplicate names")
    sensitive = [name for name in names if _SENSITIVE_ENV_NAME_RE.search(name)]
    if sensitive:
        raise ConfigError(
            f"{field_name} must not expose credential-like variables: {sensitive[0]!r}"
        )
    return names


def _choice(value: Any, field_name: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        rendered = ", ".join(sorted(choices))
        raise ConfigError(f"{field_name} must be one of: {rendered}")
    return value


def _positive_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{field_name} must be a positive finite number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ConfigError(f"{field_name} must be a positive finite number")
    return number


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{field_name} must be a positive integer")
    return value
