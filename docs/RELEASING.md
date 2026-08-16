# Release process

## Release properties

A PatchLab release must be built from the tagged commit after CI and CodeQL pass.

Do not move an existing tag. Do not use force push. Do not reuse artifacts from an earlier commit.

## Preconditions

- clean Git tree;
- version aligned in `pyproject.toml`, `_version.py`, `CITATION.cff`, and `CHANGELOG.md`;
- full unit and integration suite;
- combined line and branch coverage at or above 90 percent;
- positive and blocked Patch Passport demonstrations;
- action module-hijack E2E;
- Linux container E2E;
- Ruff, mypy, Bandit, pip-audit, and CodeQL results reviewed;
- every external GitHub Action pinned to a full commit SHA;
- wheel and source distribution built twice with equal bytes;
- clean installation of both distributions;
- deterministic SBOM and SHA-256 file;
- bounded Passport decompression and semantic identity validation;
- no known P0 or P1 issue left open without an explicit release blocker.

## Local checks

```bash
python -m compileall -q src tests scripts
PYTHONPATH=src coverage run --branch -m unittest discover -s tests -v
coverage report --show-missing --fail-under=90
python scripts/check_action_pins.py
python scripts/check_release.py
python scripts/run_demo.py --output .patchlab/release-demo
python scripts/run_attack_demo.py --output .patchlab/release-blocked
PYTHONPATH=src python -m patchlab_commons verify-passport .patchlab/release-demo/patchlab-passport.tar.gz
PYTHONPATH=src python -m patchlab_commons verify-passport .patchlab/release-blocked/patchlab-passport.tar.gz
git diff --check
```

When pinned development tools are available:

```bash
python -m pip install -r requirements-dev.txt -e .
ruff check .
ruff format --check .
mypy
bandit -r src scripts -ll
pip-audit --requirement requirements-runtime.txt
```

## Tag and hosted release

1. Merge the reviewed release commit to `main`.
2. Wait for `Required CI` and `CodeQL Python analysis` to pass.
3. Create an annotated tag, for example `v0.2.0`.
4. Push the tag without force.
5. The release workflow repeats tests and quality checks.
6. It builds wheel and source distribution twice and compares their bytes.
7. It installs both packages in clean environments.
8. It creates the source ZIP, full Git bundle, SBOM, demonstration passports, and SHA-256 list.
9. GitHub creates artifact attestations with OIDC.
10. GitHub creates a prerelease from the existing immutable tag.
11. The `Release verification` workflow downloads the assets from GitHub.
12. It requires the exact nine-file asset set and validates `SHA256SUMS.txt`.
13. It verifies every GitHub artifact attestation.
14. It installs the downloaded wheel and source distribution.
15. It verifies all three Passports, the Git bundle, `v0.1.0`, and the annotated release tag.
16. Download the same assets outside the build job and repeat the hash and attestation checks.

## PyPI Trusted Publishing

The `pypi` environment must be registered as a Trusted Publisher for:

- owner: `xordanblu`;
- repository: `patchlab-commons`;
- workflow: `release.yml`;
- environment: `pypi`.

Set repository variable `PYPI_PUBLISH_ENABLED=true` only after that registration is complete.

The PyPI job has `id-token: write` only. Do not add a long-lived PyPI token.

## Repository protection

After the hosted checks exist, require these check names on `main`:

- `Required CI`
- `CodeQL Python analysis`

Also require pull requests, resolved conversations, linear history, stale-review dismissal, no force pushes, and no branch deletion. Require one approval after a second trusted reviewer is available. Protect `v*` tags against update and deletion. Use the check names reported by GitHub.
