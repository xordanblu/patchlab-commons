from __future__ import annotations

import json
from pathlib import PurePosixPath
import re
import tomllib
from typing import Any

from ..models import Disposition, Finding, Severity
from . import CheckContext

_MANIFESTS = {
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}


def check_dependencies(context: CheckContext) -> list[Finding]:
    disposition = context.config.policy.dependency_changes
    findings: list[Finding] = []
    for item in context.changed_files:
        name = PurePosixPath(item.path).name
        if name not in _MANIFESTS:
            continue
        details = _dependency_delta(
            name,
            context.repo.file_at(context.base_sha, item.old_path or item.path),
            context.repo.file_at(context.head_sha, item.path),
        )
        message = f"Dependency metadata changed in {item.path}."
        evidence = None
        if details:
            message += f" {details}"
            evidence = details
        findings.append(
            Finding(
                rule_id="PL-DEPS-001",
                title="Dependency surface changed",
                message=message,
                severity=_severity(disposition),
                disposition=disposition,
                file=item.path,
                evidence=evidence,
                recommendation=(
                    "Review source, license, integrity, maintenance, and necessity "
                    "of every dependency change."
                ),
                tags=("dependencies", "supply-chain"),
            )
        )
    return findings


def _dependency_delta(name: str, before: str | None, after: str | None) -> str | None:
    if before is None and after is not None:
        return "The dependency file was added."
    if before is not None and after is None:
        return "The dependency file was removed."
    if before is None or after is None:
        return None
    try:
        old = _parse_dependencies(name, before)
        new = _parse_dependencies(name, after)
    except (ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return None
    if old is None or new is None:
        return None
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(key for key in set(old) & set(new) if old[key] != new[key])
    parts: list[str] = []
    if added:
        parts.append("Added: " + ", ".join(added[:10]))
    if removed:
        parts.append("Removed: " + ", ".join(removed[:10]))
    if changed:
        parts.append("Version changed: " + ", ".join(changed[:10]))
    return "; ".join(parts) if parts else None


def _parse_dependencies(name: str, text: str) -> dict[str, str] | None:
    if name == "package.json":
        data = json.loads(text)
        result: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            values = data.get(section, {})
            if isinstance(values, dict):
                result.update({str(key): str(value) for key, value in values.items()})
        return result
    if name == "pyproject.toml":
        data = tomllib.loads(text)
        result: dict[str, str] = {}
        project = data.get("project", {})
        if isinstance(project, dict):
            for raw in project.get("dependencies", []) or []:
                if isinstance(raw, str):
                    key = re.split(r"[<>=!~ ;\[]", raw, maxsplit=1)[0].strip().lower()
                    result[key] = raw
            optional = project.get("optional-dependencies", {})
            if isinstance(optional, dict):
                for group in optional.values():
                    if isinstance(group, list):
                        for raw in group:
                            if isinstance(raw, str):
                                key = re.split(r"[<>=!~ ;\[]", raw, maxsplit=1)[0].strip().lower()
                                result[key] = raw
        return result
    if name.startswith("requirements") and name.endswith(".txt"):
        result = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            key = re.split(r"[<>=!~ ;\[]", line, maxsplit=1)[0].strip().lower()
            result[key] = line
        return result
    if name == "Cargo.toml":
        data = tomllib.loads(text)
        result = {}
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            values = data.get(section, {})
            if isinstance(values, dict):
                result.update({str(key): str(value) for key, value in values.items()})
        return result
    if name == "go.mod":
        result = {}
        in_block = False
        for raw in text.splitlines():
            line = raw.strip()
            if line == "require (":
                in_block = True
                continue
            if in_block and line == ")":
                in_block = False
                continue
            if line.startswith("require "):
                parts = line.split()
                if len(parts) >= 3:
                    result[parts[1]] = parts[2]
            elif in_block and line and not line.startswith("//"):
                parts = line.split()
                if len(parts) >= 2:
                    result[parts[0]] = parts[1]
        return result
    return None


def _severity(disposition: Disposition) -> Severity:
    if disposition is Disposition.DENY:
        return Severity.ERROR
    if disposition is Disposition.REVIEW:
        return Severity.WARNING
    return Severity.INFO
