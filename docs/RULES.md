# Rule catalog

## Git and command rules

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-GIT-001` | deny | base and head resolve to the same commit |
| `PL-GIT-002` | deny | clean working tree was required but not present |
| `PL-GIT-003` | deny | Git metadata and parsed diff file counts do not match |
| `PL-POLICY-001` | review | policy differs between base and candidate |
| `PL-CMD-001` | deny | required command did not meet its exit policy |
| `PL-CMD-002` | review | optional command did not meet its exit policy |

## Scope rules

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-SCOPE-001` | deny | file-count limit exceeded |
| `PL-SCOPE-002` | deny | added-line limit exceeded |
| `PL-SCOPE-003` | deny | deleted-line limit exceeded |
| `PL-SCOPE-004` | deny | file is outside allowed scope |
| `PL-SCOPE-005` | configurable | binary file changed |
| `PL-SCOPE-006` | configurable | generated or vendored output changed |

## Dependency rule

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-DEPS-001` | review | dependency metadata or lockfile changed |

## GitHub Actions rules

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-GHA-001` | review | workflow changed |
| `PL-GHA-002` | deny | write permission added |
| `PL-GHA-003` | deny | `pull_request_target` trigger added |
| `PL-GHA-004` | deny | checkout credentials are persisted explicitly or by default |
| `PL-GHA-005` | review | failure suppression added |
| `PL-GHA-006` | deny | remote content is piped to a shell |
| `PL-GHA-007` | review | external action is not pinned by full SHA |

## Secret rules

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-SECRET-001` | deny | sensitive credential or key path changed |
| `PL-SECRET-002` | deny | private-key header added |
| `PL-SECRET-003` | deny | possible credential logging added |
| `PL-SECRET-004` | deny | possible hard-coded credential added |

## Capability and test rules

| Rule | Default decision | Meaning |
|---|---|---|
| `PL-NET-001` | review | network capability or destination added |
| `PL-TEST-001` | deny | test file deleted |
| `PL-TEST-002` | deny | assertion removed |
| `PL-TEST-003` | deny | skip or expected-failure marker added |
| `PL-TEST-004` | deny | failure suppression added |

Defaults can change through explicit policy fields only where the implementation marks a rule configurable.
