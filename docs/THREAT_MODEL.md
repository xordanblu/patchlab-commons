# Threat model

## Security objective

PatchLab must preserve the identity, integrity, and reviewability of evidence for one base-to-head comparison.

It must fail closed when it cannot provide the execution boundary requested by trusted policy.

## Actors

### Maintainer

Controls the base branch, trusted policy, workflow, release process, and final review decision.

### Contributor or coding agent

Can control the candidate commit, file names, file content, Git metadata reachable from that commit, command behavior, and command output.

### Dependency or action publisher

Can affect downloaded tools when references are mutable or package resolution is not fixed.

### CI platform

Provides the runner, token, event payload, action checkout, and artifact service. PatchLab does not defend against a fully compromised CI platform or host kernel.

## Assets

- selected base and head commit IDs;
- trusted policy bytes and digest;
- coordinator code;
- host credentials and files;
- command boundary configuration;
- command results;
- reports and Patch Passport bytes;
- release artifacts and provenance;
- repository settings and version tags.

## Trust boundaries

### Candidate repository to coordinator

All repository content is untrusted data. It cannot become executable coordinator code through imports, Python customization modules, Git configuration, hooks, filters, action inputs, or file names.

### Coordinator to command executor

The coordinator may pass only the selected snapshot, explicit command arguments, approved environment names, and bounded resource settings.

### Command executor to host

The isolated provider must not expose host secrets, arbitrary host paths, container sockets, writeable source mounts, or network access unless trusted policy explicitly enables the latter.

### Generated evidence to verifier

The verifier treats archive names, sizes, types, JSON, and digests as untrusted until every rule passes.

### Release workflow to registries

Only the dedicated release jobs can request write or OIDC permissions. Build and test jobs remain read-only.

## Attacker capabilities

A contributor can attempt to:

- add `pip`, `patchlab_commons`, `sitecustomize`, `usercustomize`, or standard-library lookalikes;
- change `PYTHONPATH`, `PYTHONHOME`, or user-site behavior;
- set hostile Git process variables;
- add hooks, filters, attributes, symlinks, gitlinks, large files, odd paths, and `export-ignore` rules;
- create unlimited output or descendant processes;
- use the network;
- read host files or sockets;
- write fake reports before the trusted coordinator finishes;
- weaken tests or policy;
- inject Markdown, SARIF, JSON, or workflow content;
- replace mutable GitHub Actions or dependencies.

## Required invariants

1. The trusted base policy determines the decision unless the maintainer explicitly selects another source.
2. Base and head resolve to exact commit object IDs.
3. Candidate files cannot change the Python code imported by the action bootstrap.
4. Candidate Git settings cannot redirect Git operations.
5. Dynamic code never runs natively without explicit consent.
6. Container mode never degrades silently to native mode.
7. Network is disabled unless trusted policy enables it.
8. Candidate code cannot write the source snapshot or evidence directory in container mode.
9. Candidate code cannot access a container-management socket.
10. Output, time, memory, CPU, PID, file-count, and byte limits remain bounded.
11. The trusted coordinator creates the final reports and bundle.
12. A verifier rejects unexpected, duplicate, unsafe, oversized, malformed, or digest-mismatched members.
13. External GitHub Actions use immutable full commit SHAs.
14. Existing release tags are never moved.

## Main mitigations

| Threat | Mitigation | Remaining limit |
|---|---|---|
| Python module replacement | isolated/no-site action entry and trusted source path | a malicious caller workflow can remove the action entirely |
| Git environment injection | minimal environment and fixed `git -c` controls | a compromised Git binary remains trusted |
| checkout/export filters | direct tree and blob materialization | unsupported gitlinks are rejected, not executed |
| host file access | isolated container with minimal read-only mount | containers share the host kernel |
| network exfiltration | `--network none` by default | explicit network mode weakens reproducibility and needs review |
| fork/process exhaustion | PID, CPU, memory, and timeout limits | platform enforcement depends on Docker/Podman and the host kernel |
| disk/output exhaustion | read-only root, bounded tmpfs, bounded captured output | container runtime metadata still consumes bounded host resources |
| evidence forgery | evidence written outside the untrusted container, then bundled and verified | SHA-256 proves bytes, not human identity |
| archive traversal | exact member set, path/type/size checks | verification still consumes bounded CPU and memory |
| mutable supply chain | exact action SHAs, fixed direct tool versions, OIDC release | transitive Python resolution is recorded but not fully hash-locked yet |

## Mode-specific claims

### Static mode

PatchLab analyzes repository changes without executing project code. It can detect configured static risks. It cannot prove that tests pass.

### Isolated container mode

PatchLab reduces direct host exposure with Linux container controls. It does not claim virtual-machine isolation or defense against a container-runtime or kernel vulnerability.

### Native mode

PatchLab applies process hygiene only. Treat the project code as trusted. Do not use this mode for unknown pull requests.

## Out of scope

- a compromised maintainer account;
- a compromised GitHub runner or host kernel;
- malicious changes to a caller workflow that simply skip PatchLab;
- complete semantic program verification;
- perfect secret detection;
- attribution of AI-generated code;
- automatic merge approval;
- hosted multi-tenant execution.
