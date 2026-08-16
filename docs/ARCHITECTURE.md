# Architecture

## Goal

PatchLab Commons creates reproducible evidence for a change between two Git commits.

The core does not require a model, network service, database, or repository write token.

## Data flow

```text
patchlab.toml
     │
     ▼
Configuration loader ───────┐
                            │
Git base ref ──► worktree ──┼─► configured commands
                            │
Git head ref ──► worktree ──┘
     │                │
     └──── Git diff ──┴─► deterministic policy checks
                              │
                              ▼
                      Verification report
                         │    │    │
                         ▼    ▼    ▼
                       JSON Markdown SARIF
                         └────┬────┘
                              ▼
                    Patch Passport bundle
                         + SHA-256
```

## Components

### Configuration loader

`src/patchlab_commons/config.py` parses TOML with the Python standard library. It validates every supported field and rejects shell-string commands.

### Git adapter

`src/patchlab_commons/gitutils.py` resolves refs, reads commit metadata, obtains diffs, and creates detached worktrees.

NUL-delimited Git metadata preserves exact paths for spaces, renames, binary files, and unusual names. Parsed diff hunks are aligned with this authoritative metadata.

Every Git command disables repository hooks, file-system monitors, global and system configuration, terminal prompts, and pagers. Unified diff generation also disables external diff and text conversion programs. Git output is spooled to temporary files and size-limited before it enters memory. A mismatch between authoritative changed-file metadata and parsed file diffs creates a blocking integrity finding.

PatchLab compares commit objects. Uncommitted working-tree files are not silently included.

### Command runner

`src/patchlab_commons/runner.py` executes argument arrays without a shell.

For each command it creates a disposable home and temporary directory. It removes unapproved environment variables, closes standard input, disables normal user configuration, captures output through temporary files, bounds stored output, redacts common credential forms, applies a timeout, and terminates the process group where supported.

This is process hygiene. It is not a complete operating-system sandbox.

Each result records:

- phase;
- command arguments;
- expected exit policy;
- exit code;
- timeout state;
- duration;
- bounded standard output and error.

### Diff parser

`src/patchlab_commons/diffparse.py` converts a unified Git diff into file and line records. Static checks inspect only additions or deletions relevant to their rule.

### Policy checks

`src/patchlab_commons/checks/` contains independent checks.

| Module | Responsibility |
|---|---|
| `scope.py` | file and line limits, binary and generated outputs |
| `dependencies.py` | manifests, lockfiles, and supported dependency deltas |
| `workflows.py` | GitHub Actions triggers, permissions, credentials, and action pinning |
| `secrets.py` | sensitive paths, key headers, hard-coded values, and logging |
| `network.py` | new network client and URL capability |
| `tests.py` | removed tests, assertions, skips, and failure suppression |

A check returns findings. It does not modify code.

### Engine

`src/patchlab_commons/engine.py` coordinates the comparison.

It:

1. resolves both refs;
2. builds the static check context;
3. executes configured commands in each required worktree;
4. creates command-failure findings;
5. calculates `pass`, `needs_review`, or `fail`;
6. writes reports;
7. creates the evidence bundle.

### Safe output

`src/patchlab_commons/safeio.py` keeps relative output below the repository root. It rejects symbolic-link redirection and writes regular files through temporary files and atomic replacement.

### Reporting

`src/patchlab_commons/reporting.py` writes JSON and Markdown. Dynamic Markdown values are flattened and enclosed in safe code spans or escaped text.

`src/patchlab_commons/sarif.py` maps findings into SARIF 2.1.0.

`src/patchlab_commons/schema.py` publishes strict JSON Schemas for the report and passport manifest.

### Passport builder

`src/patchlab_commons/passport.py` calculates SHA-256 digests and writes a deterministic archive.

The archive builder enforces member and total size limits. The verifier requires the exact member set and validates manifest types before hashing.

The archive builder normalizes:

- file order;
- timestamps;
- user and group identifiers;
- user and group names;
- file modes;
- gzip timestamp.

## Outcome rules

```text
Any deny finding              → fail
Any review finding            → needs_review
Any review finding + strict   → fail
No deny or review findings    → pass
```

A failed required command creates a deny finding.

## Extension points

New checks should remain pure where possible. They should receive `CheckContext` and return `Finding` objects.

Future isolation providers can implement the same command-result contract while using containers, virtual machines, or operating-system sandboxes.
