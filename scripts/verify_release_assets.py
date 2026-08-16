#!/usr/bin/env python3
"""Verify the exact PatchLab release asset set and its SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

_SHA256_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_NAMESPACE = re.compile(r"^https://github\.com/xordanblu/patchlab-commons/spdx/[0-9a-f]{64}$")
_MAX_SOURCE_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_SOURCE_MEMBERS = 4096
_MAX_SOURCE_MEMBER_BYTES = 32 * 1024 * 1024
_MAX_SOURCE_TOTAL_BYTES = 256 * 1024 * 1024
_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_WINDOWS_INVALID_CHARS = frozenset('<>:"\\|?*')


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_assets(version: str) -> set[str]:
    return {
        "SHA256SUMS.txt",
        "patchlab-blocked-passport.tar.gz",
        "patchlab-commons.spdx.json",
        f"patchlab-commons-v{version}-source.zip",
        f"patchlab-commons-v{version}.git.bundle",
        "patchlab-demo-pass.tar.gz",
        "patchlab-self-verification-passport.tar.gz",
        f"patchlab_commons-{version}-py3-none-any.whl",
        f"patchlab_commons-{version}.tar.gz",
    }


def _portable_source_path(name: str, prefix: str) -> PurePosixPath:
    if not name.startswith(prefix):
        raise ValueError("source ZIP has an unexpected archive root")
    relative_text = name[len(prefix) :]
    if not relative_text or "\x00" in relative_text or len(relative_text.encode("utf-8")) > 4096:
        raise ValueError(f"source ZIP contains an unsafe path: {name}")
    relative = PurePosixPath(relative_text)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_text
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"source ZIP contains an unsafe path: {name}")
    for part in relative.parts:
        if (
            len(part.encode("utf-8")) > 255
            or any(ord(character) < 32 for character in part)
            or any(character in _WINDOWS_INVALID_CHARS for character in part)
            or part.endswith((" ", "."))
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
            or part.casefold() == ".git"
        ):
            raise ValueError(f"source ZIP contains an unsafe or nonportable path: {name}")
    return relative


def _validate_symlink_target(path: PurePosixPath, target: bytes) -> None:
    try:
        text = target.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"source ZIP symlink target is not UTF-8: {path}") from exc
    if not text or "\x00" in text or "\\" in text or ":" in text:
        raise ValueError(f"source ZIP has an unsafe symlink target: {path}")
    link = PurePosixPath(text)
    if link.is_absolute():
        raise ValueError(f"source ZIP symlink escapes the archive root: {path}")
    depth = 0
    for part in (*path.parent.parts, *link.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                raise ValueError(f"source ZIP symlink escapes the archive root: {path}")
        else:
            depth += 1


def _read_member_bounded(archive: zipfile.ZipFile, member: zipfile.ZipInfo, maximum: int) -> bytes:
    collected = bytearray()
    with archive.open(member, "r") as handle:
        while True:
            chunk = handle.read(min(1024 * 1024, maximum + 1 - len(collected)))
            if not chunk:
                break
            collected.extend(chunk)
            if len(collected) > maximum:
                raise ValueError(f"source ZIP member exceeds size limit: {member.filename}")
    if len(collected) != member.file_size:
        raise ValueError(f"source ZIP member size mismatch: {member.filename}")
    return bytes(collected)


def _verify_source_zip(path: Path, version: str) -> list[str]:
    errors: list[str] = []
    if path.stat().st_size > _MAX_SOURCE_ARCHIVE_BYTES:
        return ["source ZIP exceeds the compressed size limit"]
    prefix = f"patchlab-commons-{version}/"
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if archive.comment:
                errors.append("source ZIP contains an archive comment")
            if not members:
                return ["source ZIP is empty"]
            if len(members) > _MAX_SOURCE_MEMBERS:
                return ["source ZIP exceeds the member-count limit"]
            seen: set[str] = set()
            portable_seen: set[tuple[str, ...]] = set()
            total = 0
            timestamp: tuple[int, int, int, int, int, int] | None = None
            for member in members:
                try:
                    relative = _portable_source_path(member.filename, prefix)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                portable_key = tuple(
                    unicodedata.normalize("NFC", part).casefold() for part in relative.parts
                )
                if member.filename in seen or portable_key in portable_seen:
                    errors.append(
                        "source ZIP contains a duplicate or nonportable-colliding path: "
                        + member.filename
                    )
                    continue
                seen.add(member.filename)
                portable_seen.add(portable_key)
                if member.extra or member.comment:
                    errors.append(
                        f"source ZIP member contains nondeterministic metadata: {member.filename}"
                    )
                if timestamp is None:
                    timestamp = member.date_time
                elif member.date_time != timestamp:
                    errors.append("source ZIP members do not share one deterministic timestamp")
                if member.flag_bits & 0x1:
                    errors.append(f"source ZIP contains an encrypted member: {member.filename}")
                if member.compress_type != zipfile.ZIP_DEFLATED:
                    errors.append(
                        f"source ZIP member does not use deterministic deflate: {member.filename}"
                    )
                if member.create_system != 3:
                    errors.append(f"source ZIP member lacks Unix mode metadata: {member.filename}")
                if member.is_dir():
                    errors.append(
                        f"source ZIP contains an unexpected directory entry: {member.filename}"
                    )
                    continue
                if member.file_size < 0 or member.file_size > _MAX_SOURCE_MEMBER_BYTES:
                    errors.append(f"source ZIP member exceeds size limit: {member.filename}")
                    continue
                total += member.file_size
                if total > _MAX_SOURCE_TOTAL_BYTES:
                    errors.append("source ZIP exceeds the total uncompressed size limit")
                    break
                mode = (member.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in {stat.S_IFREG, stat.S_IFLNK}:
                    errors.append(
                        f"source ZIP contains an unsupported member type: {member.filename}"
                    )
                    continue
                permissions = stat.S_IMODE(mode)
                if file_type == stat.S_IFREG and permissions not in {0o644, 0o755}:
                    errors.append(f"source ZIP contains unsafe file permissions: {member.filename}")
                if file_type == stat.S_IFLNK and permissions != 0o777:
                    errors.append(
                        f"source ZIP contains invalid symlink permissions: {member.filename}"
                    )
                if file_type == stat.S_IFLNK:
                    try:
                        target = _read_member_bounded(archive, member, 4096)
                        _validate_symlink_target(relative, target)
                    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                        errors.append(str(exc))
                else:
                    try:
                        _read_member_bounded(archive, member, _MAX_SOURCE_MEMBER_BYTES)
                    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                        errors.append(str(exc))
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        errors.append(f"source ZIP is invalid: {exc}")
    return errors


def _verify_sbom(path: Path, version: str, expected_commit: str | None) -> list[str]:
    errors: list[str] = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"SBOM is not valid UTF-8 JSON: {exc}"]
    if not isinstance(document, dict):
        return ["SBOM root is not a JSON object"]
    package_spdx = "SPDXRef-Package-patchlab-commons"
    if document.get("spdxVersion") != "SPDX-2.3":
        errors.append("SBOM does not declare SPDX-2.3")
    if document.get("SPDXID") != "SPDXRef-DOCUMENT":
        errors.append("SBOM document SPDX identifier is invalid")
    if document.get("dataLicense") != "CC0-1.0":
        errors.append("SBOM document data license is invalid")
    if document.get("name") != f"patchlab-commons-{version}":
        errors.append("SBOM document name does not match the release")
    namespace = document.get("documentNamespace")
    if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
        errors.append("SBOM document namespace is invalid")
    if document.get("documentDescribes") != [package_spdx]:
        errors.append("SBOM document description target is invalid")
    packages = document.get("packages")
    if not isinstance(packages, list) or len(packages) != 1 or not isinstance(packages[0], dict):
        return [*errors, "SBOM must describe exactly one package"]
    package = packages[0]
    required = {
        "SPDXID": package_spdx,
        "name": "patchlab-commons",
        "versionInfo": version,
        "downloadLocation": "https://github.com/xordanblu/patchlab-commons",
        "filesAnalyzed": False,
        "licenseConcluded": "Apache-2.0",
        "licenseDeclared": "Apache-2.0",
    }
    for key, value in required.items():
        if package.get(key) != value:
            errors.append(f"SBOM package field does not match the release: {key}")
    refs = package.get("externalRefs")
    if not isinstance(refs, list):
        errors.append("SBOM external references are missing")
        refs = []
    locators = {
        item.get("referenceType"): item.get("referenceLocator")
        for item in refs
        if isinstance(item, dict)
    }
    if locators.get("purl") != f"pkg:pypi/patchlab-commons@{version}":
        errors.append("SBOM package URL does not match the release")
    vcs = locators.get("vcs")
    expected_vcs = (
        f"git+https://github.com/xordanblu/patchlab-commons@{expected_commit}"
        if expected_commit is not None
        else None
    )
    if expected_vcs is not None:
        if vcs != expected_vcs:
            errors.append("SBOM VCS reference does not match the release commit")
    elif (
        not isinstance(vcs, str)
        or re.fullmatch(r"git\+https://github\.com/xordanblu/patchlab-commons@[0-9a-f]{40}", vcs)
        is None
    ):
        errors.append("SBOM VCS reference is invalid")
    relationships = document.get("relationships")
    expected_relationship = {
        "spdxElementId": "SPDXRef-DOCUMENT",
        "relationshipType": "DESCRIBES",
        "relatedSpdxElement": package_spdx,
    }
    if not isinstance(relationships, list) or expected_relationship not in relationships:
        errors.append("SBOM package relationship is invalid")
    return errors


def verify(directory: Path, version: str, expected_commit: str | None = None) -> list[str]:
    errors: list[str] = []
    if not _VERSION.fullmatch(version):
        return [f"invalid release version: {version!r}"]
    if expected_commit is not None and _COMMIT.fullmatch(expected_commit) is None:
        return [f"invalid release commit: {expected_commit!r}"]
    expected = expected_assets(version)
    try:
        actual = {path.name for path in directory.iterdir() if path.is_file()}
    except OSError as exc:
        return [f"cannot inspect release directory: {exc}"]
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append("missing release assets: " + ", ".join(missing))
    if unexpected:
        errors.append("unexpected release assets: " + ", ".join(unexpected))

    manifest = directory / "SHA256SUMS.txt"
    records: dict[str, str] = {}
    if manifest.is_file():
        try:
            lines = manifest.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"SHA256SUMS.txt is not valid UTF-8: {exc}")
            lines = []
        for line_number, line in enumerate(lines, 1):
            match = _SHA256_LINE.fullmatch(line)
            if match is None:
                errors.append(f"SHA256SUMS.txt:{line_number}: invalid checksum record")
                continue
            digest, name = match.groups()
            if name in records:
                errors.append(f"SHA256SUMS.txt:{line_number}: duplicate record for {name}")
                continue
            records[name] = digest
        expected_records = expected - {manifest.name}
        if set(records) != expected_records:
            missing_records = sorted(expected_records - set(records))
            extra_records = sorted(set(records) - expected_records)
            if missing_records:
                errors.append("checksum records missing: " + ", ".join(missing_records))
            if extra_records:
                errors.append("unexpected checksum records: " + ", ".join(extra_records))
        for name, expected_digest in records.items():
            path = directory / name
            if path.is_file() and _sha256(path) != expected_digest:
                errors.append(f"SHA-256 mismatch: {name}")

    sbom = directory / "patchlab-commons.spdx.json"
    if sbom.is_file():
        errors.extend(_verify_sbom(sbom, version, expected_commit))

    source = directory / f"patchlab-commons-v{version}-source.zip"
    if source.is_file():
        errors.extend(_verify_source_zip(source, version))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_dir():
        print(f"release directory does not exist: {directory}", file=sys.stderr)
        return 1
    errors = verify(directory, args.version, args.commit)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"verified {len(expected_assets(args.version))} exact release assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
