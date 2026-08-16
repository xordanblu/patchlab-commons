#!/usr/bin/env python3
"""Normalize source distributions when SOURCE_DATE_EPOCH is set."""

from __future__ import annotations

import copy
import gzip
import os
import shutil
import tarfile
import tempfile
from pathlib import Path


def source_date_epoch() -> int | None:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return None
    try:
        epoch = int(raw)
    except ValueError as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
    return epoch


def normalize_sdist(archive_path: Path, epoch: int) -> None:
    """Rewrite a gzip-compressed tar archive with deterministic metadata."""
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="patchlab-sdist-", dir=archive_path.parent) as raw:
        temporary = Path(raw)
        tar_path = temporary / "normalized.tar"
        gzip_path = temporary / archive_path.name
        with (
            tarfile.open(archive_path, "r:gz") as source,
            tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as target,
        ):
            members = source.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ValueError("source distribution contains duplicate members")
            for original in sorted(members, key=lambda member: member.name):
                member = copy.copy(original)
                member.mtime = epoch
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                member.pax_headers = {}
                payload = source.extractfile(original) if original.isreg() else None
                target.addfile(member, payload)
        with (
            tar_path.open("rb") as source_bytes,
            gzip_path.open("wb") as output,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=output,
                mtime=epoch,
            ) as compressed,
        ):
            shutil.copyfileobj(source_bytes, compressed)
        os.replace(gzip_path, archive_path)
