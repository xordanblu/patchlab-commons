from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
from typing import Any

from .reporting import pretty_json
from .safeio import ensure_output_directory, replace_file, safe_write_text

_REQUIRED = ("report.json", "report.md", "results.sarif")
_EXPECTED_MEMBERS = frozenset((*_REQUIRED, "passport.json"))
_MAX_COMPRESSED_BYTES = 128 * 1024 * 1024
_MAX_MEMBER_BYTES = 32 * 1024 * 1024
_MAX_TOTAL_BYTES = 96 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_IDENTITY_KEYS_V1 = {
    "project",
    "repository",
    "base_sha",
    "head_sha",
    "outcome",
    "generated_at",
    "tool_version",
    "config_source",
    "config_sha256",
}
_IDENTITY_KEYS_V2 = _IDENTITY_KEYS_V1 | {
    "execution_mode",
    "execution_boundary",
    "container_runtime",
    "container_image",
    "network_enabled",
    "unsafe_native_accepted",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_passport_bundle(output_dir: Path, identity: dict[str, Any]) -> dict[str, str]:
    ensure_output_directory(output_dir)
    schema_version = _identity_schema_version(identity)
    if schema_version is None:
        raise ValueError("passport identity is invalid")
    artifacts: dict[str, dict[str, Any]] = {}
    total_size = 0
    for name in _REQUIRED:
        path = output_dir / name
        if path.is_symlink() or not path.is_file():
            raise OSError(f"required report is not a regular file: {path}")
        raw = path.read_bytes()
        if len(raw) > _MAX_MEMBER_BYTES:
            raise ValueError(f"{name} exceeds the Patch Passport member size limit")
        total_size += len(raw)
        artifacts[name] = {"sha256": sha256_bytes(raw), "size": len(raw)}
    if total_size > _MAX_TOTAL_BYTES:
        raise ValueError("report files exceed the Patch Passport total size limit")

    passport = {
        "schema_version": schema_version,
        "identity": identity,
        "artifacts": artifacts,
        "verification": {
            "algorithm": "sha256",
            "artifact_input": "raw file bytes",
            "manifest_serialization": "UTF-8 JSON, sorted keys, 2-space indentation",
        },
    }
    passport_path = output_dir / "passport.json"
    safe_write_text(passport_path, pretty_json(passport))

    members = [output_dir / name for name in (*_REQUIRED, "passport.json")]
    bundle_path = output_dir / "patchlab-passport.tar.gz"
    _write_deterministic_tar_gz(bundle_path, members)
    bundle_digest = sha256_file(bundle_path)
    sidecar = output_dir / "patchlab-passport.tar.gz.sha256"
    safe_write_text(sidecar, f"{bundle_digest}  {bundle_path.name}\n")
    return {
        "bundle": str(bundle_path),
        "bundle_sha256": bundle_digest,
        "passport": str(passport_path),
        "sidecar": str(sidecar),
    }


def verify_passport_bundle(bundle_path: str | Path) -> tuple[bool, dict[str, Any]]:
    path = Path(bundle_path)
    try:
        if path.stat().st_size > _MAX_COMPRESSED_BYTES:
            return False, {"error": "bundle exceeds the compressed size limit"}
        with tarfile.open(path, "r:gz") as archive:
            all_members = archive.getmembers()
            if any(not member.isfile() for member in all_members):
                return False, {"error": "version 1 bundles may contain regular files only"}
            names = [member.name for member in all_members]
            if len(names) != len(set(names)):
                return False, {"error": "bundle contains duplicate member names"}
            actual_members = set(names)
            if actual_members != _EXPECTED_MEMBERS:
                missing = sorted(_EXPECTED_MEMBERS - actual_members)
                unexpected = sorted(actual_members - _EXPECTED_MEMBERS)
                return False, {
                    "error": "bundle member set is invalid",
                    "missing": missing,
                    "unexpected": unexpected,
                }
            if any(member.size < 0 or member.size > _MAX_MEMBER_BYTES for member in all_members):
                return False, {"error": "bundle member exceeds the size limit"}
            if sum(member.size for member in all_members) > _MAX_TOTAL_BYTES:
                return False, {"error": "uncompressed bundle exceeds the size limit"}

            members = {member.name: member for member in all_members}
            passport_raw = _read_member(archive, members["passport.json"])
            passport = json.loads(passport_raw.decode("utf-8"))
            if not isinstance(passport, dict):
                return False, {"error": "passport root must be an object"}
            schema_version = passport.get("schema_version")
            if schema_version not in {"1.0.0", "1.1.0"}:
                return False, {"error": "unsupported passport schema version"}
            identity = passport.get("identity")
            if not _valid_identity(identity, schema_version):
                return False, {"error": "passport identity is invalid"}
            verification = passport.get("verification")
            if not _valid_verification(verification):
                return False, {"error": "passport verification metadata is invalid"}
            artifact_specs = passport.get("artifacts", {})
            if not isinstance(artifact_specs, dict) or set(artifact_specs) != set(_REQUIRED):
                return False, {"error": "passport artifact manifest is invalid"}

            checks: dict[str, dict[str, Any]] = {}
            valid = True
            for name in _REQUIRED:
                member = members[name]
                spec = artifact_specs[name]
                if not _valid_artifact_spec(spec):
                    checks[name] = {"valid": False, "error": "invalid digest record"}
                    valid = False
                    continue
                raw = _read_member(archive, member)
                actual = sha256_bytes(raw)
                expected = spec["sha256"]
                expected_size = spec["size"]
                item_valid = actual == expected and len(raw) == expected_size
                checks[name] = {
                    "valid": item_valid,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                    "expected_size": expected_size,
                    "actual_size": len(raw),
                }
                valid = valid and item_valid
            return valid, {
                "valid": valid,
                "bundle_sha256": sha256_file(path),
                "identity": identity,
                "checks": checks,
            }
    except (OSError, tarfile.TarError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, {"error": str(exc)}


def _valid_artifact_spec(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"sha256", "size"}:
        return False
    digest = value.get("sha256")
    size = value.get("size")
    return (
        isinstance(digest, str)
        and _SHA256_RE.fullmatch(digest) is not None
        and isinstance(size, int)
        and not isinstance(size, bool)
        and 0 <= size <= _MAX_MEMBER_BYTES
    )


def _identity_schema_version(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    if set(value) == _IDENTITY_KEYS_V2 and _valid_identity(value, "1.1.0"):
        return "1.1.0"
    if set(value) == _IDENTITY_KEYS_V1 and _valid_identity(value, "1.0.0"):
        return "1.0.0"
    return None


def _valid_identity(value: Any, schema_version: str) -> bool:
    expected = _IDENTITY_KEYS_V2 if schema_version == "1.1.0" else _IDENTITY_KEYS_V1
    if not isinstance(value, dict) or set(value) != expected:
        return False
    string_fields = (
        "project",
        "repository",
        "generated_at",
        "tool_version",
    )
    if any(
        not isinstance(value.get(field), str) or not value[field].strip()
        for field in string_fields
    ):
        return False
    if not _valid_timestamp(value["generated_at"]):
        return False
    if not isinstance(value.get("base_sha"), str) or _GIT_SHA_RE.fullmatch(value["base_sha"]) is None:
        return False
    if not isinstance(value.get("head_sha"), str) or _GIT_SHA_RE.fullmatch(value["head_sha"]) is None:
        return False
    if value.get("outcome") not in {"pass", "needs_review", "fail"}:
        return False
    if value.get("config_source") not in {"base", "head", "working-tree"}:
        return False
    digest = value.get("config_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        return False
    if schema_version == "1.0.0":
        return True
    if value.get("execution_mode") not in {"static", "native", "container"}:
        return False
    if value.get("execution_boundary") not in {
        "static-no-execution",
        "weak-native",
        "isolated-container",
    }:
        return False
    if not isinstance(value.get("container_runtime"), str):
        return False
    if not isinstance(value.get("container_image"), str):
        return False
    if not isinstance(value.get("network_enabled"), bool):
        return False
    return isinstance(value.get("unsafe_native_accepted"), bool)


def _valid_verification(value: Any) -> bool:
    return isinstance(value, dict) and value == {
        "algorithm": "sha256",
        "artifact_input": "raw file bytes",
        "manifest_serialization": "UTF-8 JSON, sorted keys, 2-space indentation",
    }


def _valid_timestamp(value: str) -> bool:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _write_deterministic_tar_gz(target: Path, members: list[Path]) -> None:
    ensure_output_directory(target.parent)
    raw_tar_path: Path | None = None
    compressed_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=".patchlab-passport.",
            suffix=".tar",
            delete=False,
        ) as raw_handle:
            raw_tar_path = Path(raw_handle.name)
        with tarfile.open(raw_tar_path, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(members, key=lambda item: item.name):
                raw = path.read_bytes()
                info = tarfile.TarInfo(path.name)
                info.size = len(raw)
                info.mode = 0o644
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                archive.addfile(info, fileobj=_BytesReader(raw))

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as compressed_handle:
            compressed_path = Path(compressed_handle.name)
            with raw_tar_path.open("rb") as source:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=compressed_handle,
                    mtime=0,
                ) as compressed:
                    shutil.copyfileobj(source, compressed, length=1024 * 1024)
        replace_file(compressed_path, target)
        compressed_path = None
    finally:
        if raw_tar_path is not None:
            raw_tar_path.unlink(missing_ok=True)
        if compressed_path is not None:
            compressed_path.unlink(missing_ok=True)


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    if member.name.startswith("/") or ".." in Path(member.name).parts:
        raise tarfile.TarError("unsafe archive path")
    handle = archive.extractfile(member)
    if handle is None:
        raise tarfile.TarError(f"could not read {member.name}")
    raw = handle.read(_MAX_MEMBER_BYTES + 1)
    if len(raw) > _MAX_MEMBER_BYTES:
        raise tarfile.TarError(f"{member.name} exceeds the size limit")
    return raw


class _BytesReader:
    """Minimal read-only file object for tarfile without another full buffer."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        start = self._offset
        end = min(len(self._data), start + size)
        self._offset = end
        return self._data[start:end]
