"""Compatibility entry point for offline and legacy packaging tools."""

import runpy
from pathlib import Path

from setuptools import setup
from setuptools.command.sdist import sdist

_HELPERS = runpy.run_path(
    str(Path(__file__).resolve().parent / "scripts" / "reproducible_sdist.py")
)
normalize_sdist = _HELPERS["normalize_sdist"]
source_date_epoch = _HELPERS["source_date_epoch"]


class ReproducibleSdist(sdist):
    """Normalize setuptools' sdist after it has assembled the release tree."""

    def make_archive(self, *args: object, **kwargs: object) -> str:
        archive = super().make_archive(*args, **kwargs)
        epoch = source_date_epoch()
        if epoch is not None and archive.endswith(".tar.gz"):
            normalize_sdist(Path(archive), epoch)
        return archive


if __name__ == "__main__":
    setup(cmdclass={"sdist": ReproducibleSdist})
