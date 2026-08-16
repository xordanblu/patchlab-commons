# Security policy

## Supported versions

| Version | Security fixes |
|---|---|
| `main` | Yes |
| latest tagged release | Yes |
| older alpha releases | Best effort |

## Report a vulnerability

Do not open a public issue for an unpatched vulnerability.

Use GitHub private vulnerability reporting when it is enabled for the repository. Include:

- affected version or commit;
- operating system and Python version;
- minimal reproduction;
- security impact;
- files and functions involved;
- suggested correction, when available.

Do not include real credentials or third-party private data.

## Response targets

The maintainers aim to:

- acknowledge a complete report within 5 business days;
- validate or reject it within 10 business days;
- coordinate a correction and publication date with the reporter.

These are targets, not contractual guarantees.

## Scope

High-value areas include:

- command execution escaping the documented boundary;
- credential leakage from environment sanitization;
- unsafe archive handling;
- digest verification bypass;
- Git ref confusion that validates the wrong commits;
- SARIF or Markdown injection with security impact;
- path traversal in output or bundle processing.

False positives, missing heuristic detections, and documentation errors are normally regular bugs unless they create a concrete security boundary bypass.

## Safe testing

Use repositories and systems you own or have permission to test. Use synthetic credentials. Do not test against unrelated production systems.
