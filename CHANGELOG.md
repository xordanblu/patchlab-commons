# Changelog

All notable changes are documented here.

## [Unreleased]

### Planned

- Additional language-specific dependency parsers.
- Optional virtual-machine execution providers.
- Wider hosted adoption and maintainer pilots.

## [0.2.0] - 2026-08-16

### Security

- Added fail-closed Linux container execution for untrusted project commands.
- Added non-root execution, read-only mounts, removed capabilities, `no-new-privileges`, default-deny network access, and CPU, memory, PID, time, output, and temporary-space limits.
- Removed silent fallback to native execution.
- Required explicit acceptance of the weak native boundary.
- Hardened the composite action against `pip`, `patchlab_commons`, `sitecustomize`, `usercustomize`, `PYTHONPATH`, and same-name module replacement.
- Replaced command snapshots based on Git checkout/export behavior with direct Git object materialization.
- Added a minimal Git environment that removes repository, object, config, diff, credential, SSH, and hook overrides.
- Added strict handling for symbolic links, gitlinks, nonportable paths, invalid UTF-8 paths, file counts, and snapshot byte limits.
- Added hard Git command time limits and rejected Python, Git, or container-runtime executables located anywhere inside the declared untrusted caller workspace.
- Added bounded Passport decompression and required execution identity fields to agree with the recorded boundary.
- Added verified container cleanup after normal completion and timeout.

### Added

- Python 3.14 support.
- Execution-boundary metadata in reports and Patch Passports.
- Static, container, auto, and explicit native execution modes.
- Hosted E2E workflows for action bootstrap and Linux container isolation.
- Reproducible package build checks.
- Deterministic SPDX SBOM generation.
- GitHub artifact-attestation workflow.
- Post-release workflow that downloads assets, verifies hashes and attestations, installs both distributions, and checks the Git bundle.
- Optional PyPI Trusted Publishing through OIDC.
- `AGENTS.md`, release checks, action-pin checks, and release asset builders.

### Changed

- Renamed the import package from `patchlab` to `patchlab_commons`.
- Kept the distribution name `patchlab-commons` and command name `patchlab`.
- Updated the report and passport schemas to 1.1.0.
- Made static analysis the default execution mode.
- Preserved the historical `v0.1.0` tag without moving it.

## [0.1.0] - 2026-08-16

### Added

- `patchlab init`, `doctor`, `verify`, `verify-passport`, and `schema` commands.
- Independent base and candidate Git snapshots.
- Explicit command exit policies.
- Scope, dependency, workflow, secret, network, and test-integrity checks.
- JSON, Markdown, and SARIF outputs.
- Deterministic Patch Passport archives with SHA-256 verification.
- Composite GitHub Action.
- English and Spanish documentation.
