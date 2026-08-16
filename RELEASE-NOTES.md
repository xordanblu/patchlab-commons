# PatchLab Commons v0.2.0

PatchLab Commons v0.2.0 is an Alpha security-hardening release.

## Main changes

- Adds a fail-closed Linux container provider for untrusted verification commands.
- Keeps static analysis as the default mode.
- Requires explicit consent for the weak native execution boundary.
- Blocks network access by default.
- Applies non-root execution, a read-only root, a read-only source snapshot, removed capabilities, `no-new-privileges`, and CPU, memory, PID, time, output, and temporary-space limits.
- Replaces Git worktrees and `git archive` for command snapshots with direct Git object materialization.
- Uses a minimal Git environment, hard Git time limits, strict UTF-8 policy loading, and trusted Git executable resolution.
- Hardens the composite GitHub Action against local Python module replacement.
- Treats the complete caller `GITHUB_WORKSPACE` as untrusted for Python, Git, Docker, and Podman executable resolution.
- Rejects candidate-controlled Git, Docker, Podman, and native executable resolution.
- Bounds Passport decompression and validates that execution identity fields are consistent.
- Verifies that timed-out containers are removed.
- Renames the import package to `patchlab_commons` to avoid collision with another Python project.
- Adds Python 3.14 to the supported test matrix.
- Adds hosted E2E designs for module-hijack resistance and real Linux container isolation.
- Adds reproducible build checks, SBOM generation, GitHub artifact attestations, an explicit post-release verification dispatch, and optional PyPI Trusted Publishing.

## Compatibility

- Distribution: `patchlab-commons`
- Import package: `patchlab_commons`
- Command: `patchlab`
- Python: 3.11 through 3.14
- Native CLI: Linux, macOS, and Windows
- Isolated container provider: Linux with Docker or Podman

## Important limits

PatchLab records evidence. It does not prove that a patch is correct or safe.

Static mode does not execute project code. Native mode is not a security sandbox. Container mode reduces host exposure, but it is not a virtual-machine boundary. Human review remains required for consequential changes.

The historical `v0.1.0` tag is preserved for provenance. Do not use its composite action for untrusted pull requests. Use v0.2.0 or a reviewed full commit SHA.
