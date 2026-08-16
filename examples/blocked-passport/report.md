# Patch Passport

❌ **Outcome: `fail`**

## Identity

| Field | Value |
|---|---|
| Project | `patchlab-blocked-workflow-demo` |
| Repository | `https://github.com/patchlab/examples.git` |
| Base | `f5232c951115ad94f350d5272499e601a95d5e75` → `f5232c951115ad94f350d5272499e601a95d5e75` |
| Head | `5004d7fba488e97112b6e646d4458aa730d78f2b` → `5004d7fba488e97112b6e646d4458aa730d78f2b` |
| Generated | `2026-08-16T15:05:58Z` |
| PatchLab | `0.1.0` |

## Summary

| Metric | Count |
|---|---:|
| Changed files | 1 |
| Commands | 0 |
| Passed commands | 0 |
| Findings | 7 |
| Blocking findings | 4 |
| Review findings | 3 |

## Command evidence

No commands were configured.

## Policy findings

| Rule | Decision | Location | Finding |
|---|---|---|---|
| `PL-GHA-001` | **REVIEW** | `.github/workflows/ci.yml` | .github/workflows/ci.yml changes repository automation and its effective permissions. |
| `PL-GHA-003` | **DENY** | `.github/workflows/ci.yml:3` | pull\_request\_target can expose privileged context to untrusted pull-request data. |
| `PL-GHA-002` | **DENY** | `.github/workflows/ci.yml:5` | A GitHub Actions write permission was added: contents: write |
| `PL-GHA-007` | **REVIEW** | `.github/workflows/ci.yml:10` | actions/checkout@v4 uses a mutable tag or branch. |
| `PL-GHA-004` | **DENY** | `.github/workflows/ci.yml:12` | actions/checkout credentials are explicitly persisted in the working copy. |
| `PL-GHA-006` | **DENY** | `.github/workflows/ci.yml:13` | The workflow downloads content and executes it directly in a shell. |
| `PL-NET-001` | **REVIEW** | `.github/workflows/ci.yml:13` | A command-line network client was added. |

### Recommendations

- **PL-GHA-001:** Review the event trigger, permissions, secrets, external actions, and shell steps.
- **PL-GHA-003:** Use pull\_request with read-only permissions, or isolate all untrusted checkout and input handling.
- **PL-GHA-002:** Use read-only permissions by default and grant one narrow write permission only where required.
- **PL-GHA-007:** Pin third-party actions to a reviewed 40-character commit SHA.
- **PL-GHA-004:** Set persist-credentials to false unless a reviewed write step requires it.
- **PL-GHA-006:** Download a pinned artifact, verify its digest, and execute only after review.
- **PL-NET-001:** Document the destination, data sent, timeout, retry policy, and trust boundary.

## Changed files

| Status | File | Added | Deleted |
|---|---|---:|---:|
| `M` | `.github/workflows/ci.yml` | 11 | 2 |

---

This passport records reproducible evidence. It does not replace human review.
