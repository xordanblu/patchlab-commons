# Threat model

## Security claim

PatchLab protects the integrity and reviewability of patch evidence.

It does not contain arbitrary hostile code by itself. Configured commands execute project code. Use an operating-system sandbox when that code is untrusted.

## Assets

Important assets include:

- selected base and candidate commit identities;
- the trusted policy and its SHA-256 digest;
- command results;
- rule findings;
- report bytes;
- bundle digests;
- CI credentials and environment variables;
- host files reachable by executed code;
- maintainer attention and approval.

## Trust boundaries

### Repository content

Files, branch names, commit messages, tests, package metadata, and candidate code can be untrusted.

PatchLab loads `patchlab.toml` from the base revision by default. A change to the policy is also reported as `PL-POLICY-001`.

### Command execution

Commands come from trusted policy. The programs they start can execute code from either compared revision.

PatchLab applies these controls:

- no shell invocation;
- standard input closed;
- reduced environment;
- disposable `HOME` and temporary directory;
- user Python site disabled;
- normal Git, pip, npm, and XDG user configuration redirected or disabled;
- common credential forms redacted from stored output;
- output captured through temporary files instead of unbounded memory;
- stored output bounded with both beginning and end retained;
- per-command timeout;
- process-group termination on POSIX and process-tree termination attempt on Windows.

Remaining risk:

- project code can access the host filesystem allowed by the operating system;
- project code can use the network;
- project code can consume CPU, memory, processes, or disk before the host stops it;
- explicitly allowed environment variables can contain secrets;
- readable credential files outside the disposable home can still be reached;
- platform process-tree termination can have edge cases.

Use disposable CI workers. Use containers or virtual machines for hostile code.

### Git inspection

A repository can contain hooks, text conversion filters, and file-system monitor settings that start external programs during normal Git commands.

PatchLab invokes Git with repository hooks disabled. It disables the file-system monitor, global and system Git configuration, terminal prompts, and pagers. Unified diffs also disable external diff drivers and text conversion filters. Git output is written to temporary files and rejected when it exceeds a fixed safety limit.

Remaining risk:

- the Git binary and operating system remain trusted components;
- a hostile repository can still consume resources through large object graphs;
- PatchLab does not fetch remote objects or verify the identity of the repository owner.

### GitHub Actions

Pull-request metadata and content are untrusted.

The recommended workflow uses:

- `pull_request`;
- read-only contents;
- no persisted checkout credentials;
- no repository secrets;
- exact commit pins for third-party actions;
- a job timeout.

### Output path

A repository can contain symbolic links.

Relative PatchLab output must stay under the repository root. Existing components under that root cannot be symbolic links. Existing output files cannot be symbolic links or non-file objects. Writes use temporary regular files and atomic replacement.

### Evidence bundle

A bundle can come from an untrusted source.

The verifier:

- reads only regular files;
- requires the exact version 1 member set;
- rejects duplicates and unsafe paths;
- limits compressed, per-member, and total uncompressed size;
- validates identity and verification metadata types;
- validates SHA-256 syntax and byte-size types;
- recalculates every artifact digest from exact bytes.

## Threats and controls

| Threat | Current control | Remaining risk |
|---|---|---|
| Wrong refs verified | full commit resolution and report identity | workflow can supply the wrong refs |
| Same commit used twice | deny finding | none inside one report |
| Policy self-modification | base-revision policy, digest, visible finding | maintainer can approve a bad base policy |
| Git hook or text-filter execution | hooks, fsmonitor, external diff, and text conversion disabled | trusted Git binary and host remain in scope |
| Shell injection | argument arrays; no shell | called program can interpret arguments |
| Inherited secrets | minimal environment and disposable home | readable files or explicitly allowed variables |
| Output memory exhaustion | temporary-file capture and bounded retained text | disk can still be exhausted |
| Long-running commands | timeout and process-tree termination | platform-specific child escape |
| Secret text in output | common-pattern redaction | unknown formats can remain |
| Test weakening | deletion, assertion, skip, and suppression rules | semantic weakening can evade patterns |
| Workflow privilege increase | permission, trigger, credential, pin, and script rules | complex YAML semantics can evade line rules |
| Markdown injection | dynamic values use escaped text or safe code spans | rendering platform differences |
| Remote credential leak | repository URL credentials and local parents removed | unusual remote syntax can evade normalization |
| Output redirection | parent traversal and symbolic links rejected | privileged local race outside normal use |
| Archive traversal | exact member set and path checks | decompression still consumes bounded resources |
| Digest bypass | strict SHA-256 and exact byte-size comparison | digest does not prove creator identity |

## Out of scope for version 0.1

- complete malware containment;
- proof that tests are sufficient;
- semantic equivalence;
- model or author attribution;
- every encoded secret format;
- creator identity attestation;
- hosted multi-tenant execution;
- automatic approval or merge.

## Planned controls

- Docker and Podman execution providers;
- read-only mounts;
- default-deny network mode;
- CPU, memory, process, and disk limits;
- signed attestations;
- structured YAML parsing;
- provenance integration;
- policy approval signatures.
