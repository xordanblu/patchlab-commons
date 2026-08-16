<p align="center">
  <img src="docs/assets/logo.svg" width="680" alt="PatchLab Commons">
</p>

<p align="center">
  <strong>Evidence-first verification for software patches.</strong><br>
  Compare two Git revisions. Review new capabilities. Run bounded checks. Create a portable Patch Passport.
</p>

<p align="center">
  <a href="README.es.md">Español</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/GITHUB_ACTION.md">GitHub Action</a> ·
  <a href="docs/PATCH_PASSPORT_SPEC.md">Passport specification</a> ·
  <a href="docs/THREAT_MODEL.md">Threat model</a> ·
  <a href="SECURITY.md">Security</a>
</p>

> **Status:** `0.2.0` Alpha. The core workflow is functional and tested. PatchLab records evidence. It does not prove that a patch is correct, complete, or free of vulnerabilities. Human review remains required.

## Why PatchLab exists

A pull request can look convincing and still be unsafe.

The same person or coding agent can write a patch, add a weak test, run that test, and declare success. A line diff also leaves important questions unanswered:

- Did the reported defect exist before the patch?
- Does the same reproduction pass after the patch?
- Were tests deleted, skipped, or weakened?
- Did the patch add write permissions, network access, secrets, binaries, or dependencies?
- Which exact commits, policy, and execution boundary produced the result?

PatchLab records those answers as reviewable evidence.

## What PatchLab produces

```text
.patchlab/out/
├── report.json                     machine-readable source of truth
├── report.md                       maintainer summary
├── results.sarif                   SARIF 2.1.0 findings
├── passport.json                   artifact and identity manifest
├── patchlab-passport.tar.gz        portable evidence bundle
└── patchlab-passport.tar.gz.sha256 external integrity value
```

A **Patch Passport** binds the selected commits, trusted policy, execution identity, command results, static findings, reports, byte sizes, and SHA-256 digests into one bounded archive.

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

### Keep policy independent

Pull-request verification loads `patchlab.toml` from the **base revision by default**. A candidate cannot silently replace the policy used to judge itself.

PatchLab also materializes snapshots directly from Git tree and blob objects. It does not use checkout filters, hooks, worktrees, or `git archive`. Candidate-controlled `export-ignore` rules cannot remove files from the executed snapshot.

### Detect review risks

The deterministic rules cover:

- files and line counts outside the approved scope;
- dependency manifests and lockfiles;
- GitHub Actions changes;
- write permissions and `pull_request_target`;
- persisted checkout credentials;
- mutable third-party action references;
- downloaded scripts executed directly;
- sensitive files and possible hard-coded credentials;
- possible secret logging;
- new network clients and URLs;
- deleted tests, removed assertions, skips, and failure suppression;
- binary and likely generated artifacts;
- attempts to weaken `patchlab.toml`;
- mismatches between Git metadata and parsed diff evidence.

### Choose an execution boundary

PatchLab supports these modes:

| Mode | Executes project code | Intended use |
|---|---:|---|
| `static` | No | Default. Review changes without running candidate code. |
| `container` | Yes | Linux with Docker or Podman and a pinned image. |
| `auto` | When an isolated provider is available | Fails closed when commands are required and isolation is unavailable. |
| `native` | Yes | Trusted local code only. Requires explicit acceptance. |

Container mode uses a non-root user, a read-only root file system, a read-only source snapshot, removed Linux capabilities, `no-new-privileges`, default-deny network access, and CPU, memory, PID, time, output, and temporary-space limits.

Container mode reduces direct host exposure. It is not a virtual-machine boundary. Containers still share the host kernel.

Native mode is a weak boundary. It does not stop project code from reading files available to the current user, using the host network, or attacking the host. Do not use native mode for unknown pull requests.

## Install

PatchLab requires Python 3.11 through 3.14 and Git.

From a checked-out source tree:

```bash
python -I -m pip install --no-deps .
patchlab --version
patchlab doctor
```

For development:

```bash
python -I -m pip install -r requirements-dev.txt -e .
make verify
```

The runtime package declares no third-party Python dependencies.

## Start locally

Create a configuration and a read-only GitHub workflow:

```bash
patchlab init
```

Static verification does not execute project code:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --execution-mode static \
  --output .patchlab/out
```

Run project commands inside an isolated Linux container:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --execution-mode container \
  --container-runtime docker \
  --container-image 'python@sha256:<64-hex-digest>' \
  --no-network \
  --output .patchlab/out
```

The image must use a registry digest or an immutable local image ID.

Verify a received bundle:

```bash
patchlab verify-passport .patchlab/out/patchlab-passport.tar.gz
```

## Configuration

```toml
[project]
name = "example-project"

[execution]
mode = "static"
container_runtime = "auto"
container_image = ""
network = false
memory_mb = 1024
cpus = 1.0
pids_limit = 128
tmpfs_mb = 64
allow_unsafe_native = false

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
```

Policy decisions are `allow`, `review`, or `deny`. Unknown keys are rejected. A spelling error cannot silently select a weaker default.

See [`docs/RULES.md`](docs/RULES.md) and [`examples/patchlab.toml`](examples/patchlab.toml).

## GitHub Action

Use a published action or a separate trusted checkout. Do not use `uses: ./` from the candidate repository for an untrusted pull request.

```yaml
- uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5
  id: patchlab
  with:
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
    repository: .
    config: patchlab.toml
    config-source: base
    execution-mode: static
    output: .patchlab/out
    fail-on-review: "true"
```

The example pins the hardened action implementation to a full commit SHA. Review the selected commit before use.

The caller workflow must use `pull_request`, read-only permissions, full Git history, and no persisted checkout credentials. It must not expose secrets to candidate code.

```yaml
permissions:
  contents: read

- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with:
    fetch-depth: 0
    persist-credentials: false
```

See [`examples/github-action.yml`](examples/github-action.yml) and [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md).

## Demonstrations

A valid defect correction must pass:

```bash
python -I scripts/run_demo.py --output .patchlab/demo
patchlab verify-passport .patchlab/demo/patchlab-passport.tar.gz
```

A privileged workflow change must fail and still produce valid evidence:

```bash
python -I scripts/run_attack_demo.py --output .patchlab/blocked-demo
patchlab verify-passport .patchlab/blocked-demo/patchlab-passport.tar.gz
```

Ready-to-inspect outputs live in [`examples/sample-passport`](examples/sample-passport) and [`examples/blocked-passport`](examples/blocked-passport).

## Security boundary

PatchLab protects its coordinator from common Python import replacement and hostile Git process variables. The composite action starts Python with isolated and no-site flags. It imports only the action's own source tree. It does not run `pip` during bootstrap.

Git operations use a minimal, non-interactive environment. Replacement objects and lazy object fetches are disabled; grafts, alternate object stores, symlinked metadata, and metadata outside the repository boundary are rejected. Snapshots have file-count, member-size, total-size, path, file-mode, and symbolic-link limits.

The trusted coordinator writes and verifies final evidence outside the untrusted container.

Read [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and [`SECURITY.md`](SECURITY.md) before security-sensitive use.

## Development and validation

```bash
make compile
make test
make coverage
make demos
make checks
```

Hosted CI is configured for Python 3.11, 3.12, 3.13, and 3.14 on Linux, macOS, and Windows. Separate jobs test coverage, packaging, action bootstrap resistance, real Linux container isolation, demonstrations, and CodeQL.

A hosted check is authoritative only after it runs in GitHub. Local claims and remote evidence are kept separate in [`docs/VALIDATION.md`](docs/VALIDATION.md).

## Design principles

1. **Evidence before confidence.** A claim is not proof.
2. **Independent policy.** A patch does not define its own approval standard.
3. **Fail closed.** Missing isolation cannot silently become native execution.
4. **Least privilege.** Normal verification needs read-only repository access.
5. **Deterministic decisions.** Core approval logic does not require an AI model.
6. **Human authority.** Maintainers retain the final decision.
7. **Portable records.** Evidence remains useful outside one platform.
8. **Bilingual access.** Core user documentation exists in English and Spanish.
9. **No fake adoption.** Impact means verified external use, not purchased metrics.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
