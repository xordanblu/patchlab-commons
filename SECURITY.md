# Security policy

## Supported versions

| Version | Security fixes |
|---|---|
| `main` | Yes |
| `0.2.x` | Yes |
| `0.1.0` | No. Historical provenance only. Do not use its action for untrusted pull requests. |

## Report a vulnerability

Do not open a public issue for an unpatched vulnerability.

Use GitHub private vulnerability reporting when enabled. Include:

- affected version or commit;
- operating system, Python version, and execution mode;
- minimal reproduction with synthetic data;
- attacker capability and security impact;
- affected files and functions;
- suggested correction when available.

Do not include real credentials, private third-party data, or active exploit traffic.

## Response targets

The maintainers aim to:

- acknowledge a complete report within 5 business days;
- validate or reject it within 10 business days;
- coordinate a correction and publication date with the reporter.

These are targets, not contractual guarantees.

## High-value scope

- action bootstrap importing code from the caller repository;
- container escape from documented controls;
- silent fallback to native execution;
- host file, secret, network, or container-socket exposure;
- Git environment or object redirection;
- snapshot path, symbolic-link, gitlink, or size-limit bypass;
- output path or archive traversal;
- Patch Passport digest, identity, or member validation bypass;
- verification of the wrong commits or policy;
- evidence written or replaced by untrusted command code;
- release or action supply-chain compromise.

A missing heuristic detection is normally a regular bug unless it bypasses a documented security invariant.

## Safe testing

Use repositories and systems you own or have written permission to test. Use synthetic credentials. Do not test unrelated production systems.

Container mode is designed for hostile repository code, but it is not a virtual-machine boundary. Do not test kernel or container-runtime exploits through the public project workflow.
