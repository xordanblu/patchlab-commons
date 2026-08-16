# Contributing

Thank you for helping PatchLab Commons.

## Before you start

Open an issue for a large change. Small corrections can go directly to a pull request.

Security vulnerabilities must follow [`SECURITY.md`](SECURITY.md). Do not publish an active vulnerability in a public issue.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
make compile
make test
make demo
make attack-demo
make coverage
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Pull-request requirements

A pull request must:

- have one clear purpose;
- include tests for changed behavior;
- preserve backward compatibility or explain the break;
- update English and Spanish user documentation when the user interface changes;
- avoid unrelated formatting changes;
- avoid generated files unless the generation process is documented;
- pass the complete test suite;
- state whether an AI coding tool was used;
- confirm that the author reviewed and understands every submitted line.

Using an AI tool is allowed. Delegating responsibility is not.

## Adding a rule

Each new rule must include:

1. A stable rule ID.
2. A narrow threat or quality claim.
3. At least one positive test.
4. At least one negative test.
5. A clear recommendation.
6. A documented false-positive limit.
7. A default disposition of `review` unless blocking is strongly justified.

## Commit style

Use a direct imperative subject.

Examples:

```text
Add Cargo dependency delta parsing
Reject private-key files in scope check
Document Windows worktree behavior
```

## Developer Certificate of Origin

By contributing, you certify that you have the right to submit the work under the project license. Add a sign-off when your organization or contribution process requires it.
