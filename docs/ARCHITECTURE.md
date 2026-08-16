# Architecture

## Goal

PatchLab Commons creates reviewable evidence for a change between two Git commits.

The core does not require a model, network service, database, or repository write token.

## Trust model

PatchLab separates four kinds of data:

1. **Trusted coordinator code.** The installed CLI or published action.
2. **Trusted policy.** `patchlab.toml` from the selected base revision by default.
3. **Untrusted repository data.** Commit trees, diffs, paths, source files, and command output.
4. **Generated evidence.** Reports and the Patch Passport, written by the coordinator outside the untrusted command boundary.

The candidate revision never gains policy authority merely because it contains instructions or configuration text.

## Data flow

```text
trusted base policy ───────────────┐
                                  │
Git base commit ─► object snapshot├─► static checks
Git head commit ─► object snapshot│
                                  ├─► optional isolated commands
Git diff ─────────────────────────┘
                                  │
                                  ▼
                         trusted coordinator
                                  │
                       JSON / Markdown / SARIF
                                  │
                                  ▼
                     Patch Passport + SHA-256
```

## Components

### Configuration loader

`src/patchlab_commons/config.py` parses TOML with the Python standard library.
It rejects unknown fields, shell-string commands, mutable container image tags, invalid limits, credential-like environment grants, and native execution without explicit consent.

### Git adapter

`src/patchlab_commons/gitutils.py` resolves refs and reads Git objects through a minimal process environment.

It removes or overrides variables that can redirect the repository, object database, index, configuration, hooks, diff tools, SSH, or credentials. It disables prompts, pagers, hooks, external diff, text conversion, file protocol access, and file-system monitors.

It also disables replacement objects and lazy object fetching, and rejects grafts, alternate object stores, symlinked Git metadata, and metadata paths outside the declared untrusted repository boundary. This keeps object lookup inside the repository that was placed in scope.

Command snapshots do not use `git checkout`, a worktree, or `git archive`. PatchLab reads the selected tree and blob objects directly. This prevents checkout filters, hooks, and `export-ignore` rules from changing the code that is executed.

The materializer:

- applies file-count, per-file, and total-byte limits;
- rejects gitlinks and unsupported modes;
- rejects `.git`, absolute, parent, nonportable, and invalid UTF-8 paths;
- writes ordinary files before symbolic links;
- rejects symbolic links that escape the snapshot;
- never includes Git metadata.

### Command runner

`src/patchlab_commons/runner.py` supports three boundaries.

#### Static

Static mode does not execute project code. It is the default.

#### Isolated container

Linux container mode uses Docker or Podman with:

- an immutable image digest or local image ID;
- a fixed non-root user;
- all Linux capabilities removed;
- `no-new-privileges`;
- a read-only root file system;
- a read-only source snapshot;
- network disabled by default;
- CPU, memory, PID, timeout, output, and temporary-space limits;
- no Docker or Podman socket;
- no host secrets or arbitrary environment inheritance.

Base and head commands run in separate disposable containers. The trusted process creates evidence after each command exits.

#### Native

Native mode uses argument arrays without a shell. It cleans the environment, creates a disposable home and temporary directory, bounds output, applies a timeout, and terminates descendant processes where supported.

Native mode is a weak boundary. It does not stop project code from reading files available to the current user, using the host network, or attacking the host kernel. It requires explicit `allow_unsafe_native = true`.

### Composite action bootstrap

`scripts/action_entry.py` runs with Python isolated and no-site flags from the action directory. It imports `patchlab_commons` only from the action's own `src` directory.

The action does not run `pip`, `python -m patchlab_commons`, inline Python, or package discovery from the caller repository during bootstrap. It rejects `uses: ./` when the action itself is inside the candidate repository.

### Policy checks

`src/patchlab_commons/checks/` contains deterministic checks for:

- scope and size;
- dependency changes;
- workflow permissions and triggers;
- action pinning and checkout credentials;
- possible secrets;
- new network capability;
- test deletion or weakening;
- binary and generated outputs;
- policy self-modification.

Checks return findings. They do not modify code.

### Engine

`src/patchlab_commons/engine.py`:

1. resolves base and head commits;
2. loads policy from the trusted source;
3. calculates the authoritative changed-file set and diff;
4. runs deterministic checks;
5. selects one execution boundary;
6. executes required evidence commands when allowed;
7. calculates `pass`, `needs_review`, or `fail`;
8. writes reports through the trusted coordinator;
9. creates and verifies the Patch Passport.

### Safe output and evidence

`safeio.py` rejects parent traversal and symbolic-link redirection. It uses atomic replacement for regular output files.

`passport.py` enforces an exact archive member set, member types, byte limits, safe paths, SHA-256 digests, and schema-valid identity data. The archive profile normalizes order, timestamps, ownership, and modes.

## Outcome rules

```text
Any deny finding                    -> fail
Any review finding                  -> needs_review
Any review finding + strict policy  -> fail
No deny or review finding           -> pass
```

A missing safe executor is a deny finding when dynamic commands are required.

## Platform support

- CLI and static checks: Linux, macOS, and Windows.
- Native boundary: Linux, macOS, and Windows, with platform-specific process limits.
- Isolated container boundary: Linux with Docker or Podman.

## Non-claims

PatchLab does not prove:

- complete malware containment;
- correctness of the patch;
- completeness of the tests;
- author identity;
- semantic equivalence;
- absence of every secret or vulnerability.
