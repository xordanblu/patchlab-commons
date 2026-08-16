# GitHub Action guide

## Safe baseline

Use `pull_request`, read-only permissions, full Git history, and no persisted checkout credentials.

Every external action below is pinned to a reviewed 40-character commit SHA.

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
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.14"

      - name: Verify patch without executing project code
        id: patchlab
        uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          repository: .
          config: patchlab.toml
          config-source: base
          execution-mode: static
          output: .patchlab/out
          fail-on-review: "false"

      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always()
        with:
          name: patchlab-passport
          path: .patchlab/out/
          if-no-files-found: error
```

The full SHA points to the reviewed v0.2.0 security core. Dependabot can propose later SHA updates.

## Dynamic verification

Static mode does not run configured project commands.

To run them, use a Linux runner and a digest-pinned image:

```yaml
      - name: Verify patch in an isolated container
        uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
          config-source: base
          execution-mode: container
          container-runtime: docker
          container-image: ghcr.io/example/project-test@sha256:<64 lowercase hex characters>
          network: "false"
          fail-on-review: "true"
```

The image must already contain every tool needed by the configured commands. PatchLab does not install candidate dependencies during bootstrap.

## Inputs

| Input | Required | Default | Meaning |
|---|---:|---|---|
| `base` | yes | none | trusted base Git ref or commit |
| `head` | yes | none | candidate Git ref or commit |
| `repository` | no | `.` | checked-out repository below `GITHUB_WORKSPACE` |
| `config` | no | `patchlab.toml` | policy path relative to the repository |
| `config-source` | no | `base` | `base`, `head`, or `working-tree` |
| `output` | no | `.patchlab/out` | report directory below the repository |
| `fail-on-review` | no | `true` | convert review findings into job failure |
| `execution-mode` | no | `static` | `static`, `auto`, or `container` |
| `container-runtime` | no | `auto` | `auto`, `docker`, or `podman` |
| `container-image` | no | empty | immutable image digest or local image ID |
| `network` | no | `false` | enable network inside the command container |

The action never permits native mode.

## Outputs

- `outcome`: `pass`, `needs_review`, or `fail`.
- `report`: `report.json` path.
- `markdown`: `report.md` path.
- `sarif`: `results.sarif` path.
- `passport`: `passport.json` path.
- `bundle`: verified bundle path.
- `bundle-sha256`: verified bundle digest.
- `sidecar`: digest sidecar path.
- `exit-code`: `0` or `1`.

The action derives outputs from the in-memory trusted result. It verifies the bundle before publishing paths or digests.

## Bootstrap boundary

The action runs its entry point with Python `-I -S` from `github.action_path`. It does not use `pip`, module discovery, inline Python, or the caller directory during bootstrap.

Do not invoke the action as `uses: ./` from the same untrusted repository. The action rejects that layout. Use the published action or a separately checked-out trusted copy.

## Fork pull requests

Keep all of these properties:

- event `pull_request`;
- no `pull_request_target`;
- `contents: read` only;
- no repository, cloud, package, or deployment secrets;
- `persist-credentials: false`;
- no publication or deployment step;
- a bounded timeout;
- isolated container mode for untrusted commands.
