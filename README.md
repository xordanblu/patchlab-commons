<p align="center">
  <img src="docs/assets/logo.svg" width="680" alt="PatchLab Commons">
</p>

<p align="center">
  <strong>Evidence-first verification for software patches.</strong><br>
  Compare two Git revisions. Run trusted checks. Detect risky changes. Create a portable Patch Passport.
</p>

<p align="center">
  <a href="README.es.md">Español</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/PATCH_PASSPORT_SPEC.md">Passport specification</a> ·
  <a href="docs/THREAT_MODEL.md">Threat model</a> ·
  <a href="SECURITY.md">Security</a>
</p>

> **Status:** `0.1.0-alpha`. The complete core workflow is functional and tested. PatchLab is an evidence tool. It is not a proof of correctness or a replacement for human review.

## Why PatchLab exists

A pull request can look convincing and still be unsafe.

The same person or coding agent can write a patch, add a weak test, run that test, and declare success. A normal line diff also hides important questions:

- Did the reported defect exist before the patch?
- Does the same reproduction pass after the patch?
- Were tests deleted, skipped, or weakened?
- Did the patch add write permissions, network access, secrets, binaries, or dependencies?
- Which exact commits and policy produced the approval result?

PatchLab records answers as reviewable evidence.

## What it produces

```text
.patchlab/out/
├── report.json                     machine-readable source of truth
├── report.md                       maintainer summary
├── results.sarif                   SARIF 2.1.0 findings
├── passport.json                   artifact digest manifest
├── patchlab-passport.tar.gz        portable evidence bundle
└── patchlab-passport.tar.gz.sha256 external integrity value
```

A **Patch Passport** binds the selected commits, trusted policy, command results, static findings, reports, byte sizes, and SHA-256 digests into one bounded archive.

## Core capabilities

### Reproduce before and after

A command can be required to fail on the base revision and pass on the candidate revision.

```toml
[[commands]]
name = "regression"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 120
required = true
```

### Run independent verification

PatchLab can run tests, builds, linters, or project-specific scripts from policy stored in the trusted base revision.

Commands are argument arrays. PatchLab does not invoke a shell.

### Detect review risks

The current rules cover:

- files and line counts outside the approved scope;
- dependency manifests and lockfiles;
- GitHub Actions workflow changes;
- write permissions and `pull_request_target`;
- persisted checkout credentials;
- mutable third-party action references;
- downloaded scripts executed directly;
- sensitive files and possible hard-coded credentials;
- possible secret logging;
- new network clients and URLs;
- deleted test files and removed assertions;
- new skips, expected failures, and failure suppression;
- binary and likely generated artifacts;
- attempts to weaken `patchlab.toml` inside the candidate patch;
- mismatches between Git's changed-file metadata and parsed diff evidence.

### Create verifiable output

The archive format normalizes file order, timestamps, ownership, permissions, and gzip metadata. The verifier rejects unexpected members, duplicate names, unsafe paths, malformed digest records, and oversized content.

PatchLab publishes strict JSON Schemas for both `report.json` and `passport.json`.

## Fast local start

PatchLab requires Python 3.11 or newer and Git.

```bash
git clone https://github.com/xordanblu/patchlab-commons.git
cd patchlab-commons
python -m pip install -e .
patchlab --version
patchlab doctor
```

Create a configuration and a read-only GitHub workflow:

```bash
patchlab init
```

Compare two commits:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --output .patchlab/out
```

Verify a received bundle:

```bash
patchlab verify-passport .patchlab/out/patchlab-passport.tar.gz
```

## Two end-to-end demonstrations

A valid defect correction must pass:

```bash
python scripts/run_demo.py --output .patchlab/demo
```

A privileged workflow change must fail and still produce valid evidence:

```bash
python scripts/run_attack_demo.py --output .patchlab/blocked-demo
```

The blocked demonstration detects write permission, `pull_request_target`, persisted credentials, an unpinned action, remote script execution, and new network access.

Ready-to-inspect outputs live in [`examples/sample-passport`](examples/sample-passport) and [`examples/blocked-passport`](examples/blocked-passport).

## Configuration

Pull-request verification loads `patchlab.toml` from the **base revision by default**. A candidate cannot silently replace the policy used to judge itself.

For a first installation, merge `patchlab.toml` into the default branch before enabling the pull-request workflow. Later runs can then load the trusted policy from the base revision.

```toml
[project]
name = "example-project"

[scope]
allow = ["src/**", "tests/**", "pyproject.toml", ".github/workflows/**"]
deny = ["**/*.pem", "**/*.key", ".env", ".env.*"]
max_files = 60
max_added_lines = 2500
max_deleted_lines = 2500

[policy]
dependency_changes = "review"
workflow_changes = "review"
dangerous_permissions = "deny"
secret_exposure = "deny"
network_additions = "review"
test_weakening = "deny"
binary_files = "review"
generated_files = "review"
fail_on_review = false
require_clean_worktree = false
require_human_review = true

[[commands]]
name = "tests"
command = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 300
required = true
```

Policy decisions are `allow`, `review`, or `deny`.

PatchLab rejects unknown configuration keys. A spelling error cannot silently fall back to a weaker default.

See [`docs/RULES.md`](docs/RULES.md) and [`examples/patchlab.toml`](examples/patchlab.toml).

## GitHub Action

```yaml
- uses: xordanblu/patchlab-commons@v0.1.0
  id: patchlab
  with:
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
    repository: .
    config: patchlab.toml
    config-source: base
    output: .patchlab/out
    fail-on-review: "true"
```

The checkout must contain full history and must not persist credentials:

```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
  with:
    fetch-depth: 0
    persist-credentials: false
```

The included action appends `report.md` to the GitHub job summary and exposes paths for JSON, SARIF, passport, bundle, digest, outcome, and exit code.

See [`examples/github-action.yml`](examples/github-action.yml) and [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md).

## Security boundary

PatchLab reduces inherited environment variables. It uses a disposable home and temporary directory for each command. It removes normal user configuration, closes standard input, bounds captured output, redacts common credential forms, applies timeouts, and terminates the command process group on supported systems.

PatchLab also disables Git hooks, file-system monitors, external diff programs, text conversion filters, global configuration, prompts, and pagers during repository inspection.

Configured commands still execute project code. Git worktrees separate revisions. They are **not** an operating-system sandbox.

Use disposable CI workers. Use a container or virtual machine when the compared code is not trusted. Never expose repository secrets to a pull-request verification job.

Output paths inside the repository cannot traverse parents or follow symbolic links. Bundle verification is read-only and bounded.

Read [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) before using PatchLab for security-sensitive review.

## Design principles

1. **Evidence before confidence.** A claim is not proof.
2. **Independent policy.** A patch does not define its own approval standard.
3. **Least privilege.** Normal verification needs read-only repository access.
4. **Deterministic decisions.** Core approval logic does not require an AI model.
5. **Human authority.** Maintainers retain the final decision.
6. **Portable records.** Evidence remains useful outside one platform.
7. **Bilingual access.** Core user documentation exists in English and Spanish.
8. **No fake adoption.** Impact means verified external use, not purchased metrics.

## Development

```bash
python -m pip install -e ".[dev]"
make compile
make coverage
make demo
make attack-demo
make build
```

The runtime package has no third-party Python dependencies.

CI tests Python 3.11, 3.12, and 3.13 on Linux, macOS, and Windows. It also builds the wheel, enforces coverage, runs both demonstrations, and performs CodeQL analysis.

## Project documents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PATCH_PASSPORT_SPEC.md`](docs/PATCH_PASSPORT_SPEC.md)
- [`docs/report.schema.json`](docs/report.schema.json)
- [`docs/passport.schema.json`](docs/passport.schema.json)
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
- [`docs/RULES.md`](docs/RULES.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/IMPACT.md`](docs/IMPACT.md)
- [`GOVERNANCE.md`](GOVERNANCE.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`SUPPORT.md`](SUPPORT.md)
- [`docs/RELEASING.md`](docs/RELEASING.md)

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
