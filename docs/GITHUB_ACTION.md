# GitHub Action guide

## Safe baseline

PatchLab needs the full history for both selected commits.

```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
  with:
    fetch-depth: 0
    persist-credentials: false
```

Use read-only permissions:

```yaml
permissions:
  contents: read
```

Use `pull_request`, not `pull_request_target`, for untrusted contributor code.

Do not expose repository secrets to the verification job.

## Complete example

```yaml
name: PatchLab Passport

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read

jobs:
  passport:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: "3.12"

      # Install target-project dependencies here when its tests need them.

      - name: Verify patch
        id: patchlab
        uses: xordanblu/patchlab-commons@v0.1.0
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          repository: .
          config: patchlab.toml
          config-source: base
          output: .patchlab/out
          fail-on-review: "true"

      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        if: always()
        with:
          name: patchlab-passport
          path: .patchlab/out/
          if-no-files-found: error
```

## Inputs

| Input | Required | Default | Meaning |
|---|---:|---|---|
| `base` | yes | none | trusted base Git ref or commit |
| `head` | yes | none | candidate Git ref or commit |
| `repository` | no | `.` | checked-out repository directory |
| `config` | no | `patchlab.toml` | policy file relative to the repository |
| `config-source` | no | `base` | revision that supplies policy |
| `output` | no | `.patchlab/out` | report directory |
| `fail-on-review` | no | `true` | fail the job for `review` findings |

`config-source: base` is the safe pull-request default. It stops the candidate revision from replacing its own approval policy.

The first installation is a bootstrap change. Merge `patchlab.toml` and the workflow into the default branch before using `config-source: base` on later pull requests. A policy that exists only in the candidate revision is not trusted by the safe default.

## Outputs

| Output | Meaning |
|---|---|
| `outcome` | `pass`, `needs_review`, or `fail` |
| `report` | path to `report.json` |
| `markdown` | path to `report.md` |
| `sarif` | path to `results.sarif` |
| `passport` | path to `passport.json` |
| `bundle` | path to `patchlab-passport.tar.gz` |
| `bundle-sha256` | bundle digest |
| `sidecar` | path to `patchlab-passport.tar.gz.sha256` |
| `exit-code` | PatchLab process exit code |

The action also appends `report.md` to the GitHub job summary.

## Project dependencies

PatchLab does not guess a package manager.

Install only the dependencies needed by your configured commands. Avoid setup steps that read contributor-controlled package scripts with secrets or write permissions available.

For untrusted code, use an ephemeral runner. A container or virtual machine provides a stronger boundary than a normal hosted job.

## Fork pull requests

GitHub fork content is untrusted.

Keep these properties:

- event: `pull_request`;
- `contents: read` only;
- no repository secrets;
- no cloud credentials;
- `persist-credentials: false`;
- no deployment or publication step;
- bounded job timeout.

Artifact upload is acceptable because the standard workflow token does not need repository-content write access for that operation.

## Policy protection

Require owner review for:

- `patchlab.toml`;
- the PatchLab workflow;
- test runner scripts;
- dependency installation scripts;
- release workflows;
- `action.yml` when PatchLab is used from the same repository.

The repository includes a `CODEOWNERS` baseline for these files.

## Pin external actions

Use a reviewed 40-character commit SHA.

A major tag such as `@v4` is readable, but it can move. Keep the release tag as a comment so Dependabot can still identify the intended line.
