# AGENTS.md

## Purpose

PatchLab Commons creates reviewable evidence for changes between two Git commits.
It must fail closed when a required security boundary is unavailable.

## Architecture

- `src/patchlab_commons/config.py`: trusted policy parsing.
- `src/patchlab_commons/gitutils.py`: minimal Git environment and direct object snapshots.
- `src/patchlab_commons/runner.py`: static, isolated-container, and explicit weak-native execution.
- `src/patchlab_commons/engine.py`: verification coordination and outcomes.
- `src/patchlab_commons/passport.py`: deterministic Patch Passport creation and verification.
- `scripts/action_entry.py`: trusted composite-action bootstrap.
- `scripts/verify_release_assets.py`: exact release asset and checksum validation.
- `.github/workflows/`: CI, CodeQL, release, and post-release verification.

## Required checks

Run these before every commit that changes product code:

```bash
python -m compileall -q src tests scripts
PYTHONPATH=src coverage run --branch -m unittest discover -s tests -v
coverage report --fail-under=90
python scripts/check_action_pins.py
python scripts/check_release.py

git diff --check
```

Run Ruff, mypy, Bandit, pip-audit, package builds, demos, and clean-install tests when the pinned development tools are available.

## Controls that must not be weakened

- Do not execute untrusted project code outside the isolated provider by default.
- Do not add a silent fallback from container mode to native mode.
- Native mode must require explicit `allow_unsafe_native = true`.
- Container images must use an immutable digest or local image ID.
- Keep network access disabled by default.
- Keep the container root and source snapshot read-only.
- Do not mount Docker or Podman sockets.
- Keep CPU, memory, PID, time, output, file-count, and byte limits.
- Do not inherit arbitrary Python, Git, Docker, or Podman environment variables.
- Reject Python, Git, and container-runtime executables resolved anywhere inside the declared untrusted caller workspace.
- Keep hard time limits on Git commands and verify container removal after timeouts.
- Do not use a shell for configured project commands.
- Do not load policy from the candidate revision by default.
- Do not trust report files that candidate code can write.
- Keep archive member, path, size, type, and digest validation strict.
- Pin every external GitHub Action to a full 40-character commit SHA.
- Do not use `pull_request_target` for untrusted code.
- Do not expose secrets or write tokens to verification jobs.

## Release rules

- Keep English and Spanish user documentation aligned.
- Do not move an existing version tag.
- Do not use force push.
- Do not publish with pending or failed CI or CodeQL checks.
- Build release artifacts from the tagged commit.
- Rebuild all artifacts after any code change.
- Build the exact release asset set and verify `SHA256SUMS.txt` before upload.
- Download the published assets and verify every hash and GitHub attestation again.
- Verify wheel and source-distribution installation in clean environments.
- Use GitHub OIDC for artifact attestations and PyPI Trusted Publishing. Do not store a long-lived PyPI token.
- Keep version values aligned in `pyproject.toml`, `_version.py`, `CITATION.cff`, and `CHANGELOG.md`.
