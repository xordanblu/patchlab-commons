# Validation record — v0.1.0-alpha

Date: 2026-08-16

This record describes the checks completed before the first PatchLab Commons release candidate. It records evidence, not a claim of perfect correctness.

## Verified release surface

- CLI commands: `init`, `doctor`, `verify`, `verify-passport`, and `schema`.
- Trusted-base configuration loading.
- Detached base and candidate Git worktrees.
- Required and optional command policies.
- Scope, dependency, workflow, secret, network, and test-integrity checks.
- JSON, Markdown, SARIF, passport manifest, archive, sidecar, and SHA-256 output.
- Composite GitHub Action contract.
- English and Spanish user documentation.
- Wheel and source-distribution metadata.

## Automated tests

The final local suite executed 111 unit and integration tests.

```text
Ran 111 tests
OK
```

Branch-aware coverage over `src/patchlab` was 91%.

```text
TOTAL  1664 statements  560 branches  91% combined coverage
```

The public CI matrix is configured for Python 3.11, 3.12, and 3.13 on Linux, macOS, and Windows. Local execution validates the current environment. The hosted matrix becomes authoritative only after GitHub Actions runs in the published repository.

## End-to-end evidence

### Safe correction

The positive demonstration creates a calculator defect in the base commit. The same regression test fails on the base and passes on the candidate.

- Expected result: `pass`
- Recorded result: `pass`
- Required commands: 3 of 3 passed
- Example: `examples/sample-passport/`
- Bundle SHA-256: `f600bbb7c4c6d365e046e16b373907afe0cebff5bc3fa2d37c12885cd769958d`

### Privileged workflow change

The negative demonstration adds a privileged GitHub Actions workflow.

- Expected result: `fail`
- Recorded result: `fail`
- Detected rules: `PL-GHA-001`, `PL-GHA-002`, `PL-GHA-003`, `PL-GHA-004`, `PL-GHA-006`, `PL-GHA-007`, and `PL-NET-001`
- Example: `examples/blocked-passport/`
- Bundle SHA-256: `7151f3e370842635a9d88f31fb9576a3a570c9938d70dadbb723687f1e5c31ee`

Both bundles passed independent verification through `patchlab verify-passport`.

## Composite action simulation

The composite action shell was parsed and checked with `bash -n`.

A local runner simulation supplied the same environment values that GitHub Actions supplies to the verification step.

- Safe correction: action exit `0`, output `pass`, valid bundle, and Markdown job summary.
- Privileged workflow: action exit `1`, output `fail`, valid bundle, and Markdown job summary.
- The action emitted all documented outputs: report, Markdown, SARIF, passport, archive, sidecar, digest, outcome, and exit code.

Official GitHub actions referenced by this repository are pinned to exact commit SHAs.

## Format checks

- Report and passport JSON Schemas passed Draft 2020-12 schema checks.
- Both public example reports validate against the committed schemas.
- GitHub workflow, action, Dependabot, issue-template, and example YAML files parse successfully.
- The documentation landing page parses as HTML.
- The composite action shell parses as Bash.

## Distribution checks

The wheel was installed into a clean virtual environment with `--no-deps`.

The installed package then completed these checks:

```text
patchlab --version
patchlab schema --kind report
python scripts/run_demo.py
patchlab verify-passport <bundle>
```

The runtime wheel declares no third-party runtime dependencies. Development tools remain optional.

## Security checks completed

The test suite covers these failure modes:

- candidate policy self-weakening;
- Git metadata and parsed-diff mismatch;
- path names with spaces, renames, unusual text, and binary files;
- repository hooks and Git text-conversion filters;
- oversized Git output;
- inherited secret environment variables;
- credentials in command arguments, output, and URLs;
- unbounded command output;
- command timeout and process-tree termination;
- output traversal and symbolic-link redirection;
- malformed, oversized, duplicated, unexpected, and modified passport contents;
- unsafe GitHub permissions, triggers, credentials, mutable action references, and remote shell execution.

## Project self-verification

PatchLab compared the initial core commit `f6f15de` with commit `a5875d3` by using the policy stored in the base revision.

- Outcome: `pass`
- Changed files: 5
- Required commands: 2 of 2 passed
- Findings: 0
- Bundle verification: valid
- Bundle SHA-256: `ffdfa57fd63131c8e09b510ff6115fb47e6b3fd7c5a31d2239edc3188ac4cf55`

This bundle verifies the stated commit range. The later commit that records this result is intentionally outside that range.

## Known limits

PatchLab executes configured project commands. Detached worktrees are not an operating-system sandbox.

Version 0.1 uses conservative text rules for several semantic checks. Complex workflow or language behavior can require human review. A valid passport proves internal artifact consistency. It does not prove creator identity, test sufficiency, or total patch correctness.

See `docs/THREAT_MODEL.md` for the complete boundary.

---

## Resumen en español

La versión 0.1.0-alpha pasó 111 pruebas con 91% de cobertura combinada de líneas y ramas. La demo segura terminó en `pass`. La demo con permisos peligrosos terminó en `fail`. Ambos paquetes pasaron la verificación de SHA-256 y estructura. La acción de GitHub también pasó una simulación local para los dos resultados.

PatchLab registra evidencia verificable. No sustituye la revisión humana. Tampoco aísla por completo el código ejecutado.
