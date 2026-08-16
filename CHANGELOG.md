# Changelog

All notable changes are documented here.

## [Unreleased]

### Planned

- Container-backed command isolation.
- Pull-request annotations.
- Additional dependency-manifest parsers.
- Signed attestations.

## [0.1.0] - 2026-08-16

### Added

- `patchlab init`, `doctor`, `verify`, `verify-passport`, and `schema` commands.
- Independent base and candidate Git worktrees.
- Explicit command exit policies.
- Scope, dependency, workflow, secret, network, and test-integrity checks.
- JSON, Markdown, and SARIF outputs.
- Deterministic Patch Passport archives with SHA-256 verification.
- Composite GitHub Action.
- End-to-end safe and unsafe integration tests.
- English and Spanish documentation.
- Base-revision policy loading and policy self-modification detection.
- Exact NUL-delimited handling for spaces, renames, and binary paths.
- Strict configuration keys and types.
- Disposable command home and temporary directories.
- Bounded output capture, common-secret redaction, and process-tree termination.
- Safe output paths with symbolic-link rejection and atomic writes.
- Strict bundle member, type, digest, and size validation.
- Markdown injection defenses for untrusted file names.
- Credential-safe repository identifiers.
- Git hook, file-system monitor, external diff, and text-conversion suppression.
- Public JSON Schemas for reports and passport manifests.
- Bounded Git output and metadata-to-diff integrity checks.
- Full composite-action outputs and exact commit pins for official actions.
- Valid and blocked end-to-end demonstrations.
- CI across Python 3.11–3.13 on Linux, macOS, and Windows.
