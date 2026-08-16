# Governance

PatchLab Commons uses a maintainer-led, evidence-based governance model.

## Roles

### Users

Users run PatchLab and report defects or missing use cases.

### Contributors

Contributors submit documentation, tests, rules, code, and design proposals.

### Maintainers

Maintainers review contributions, publish releases, manage security reports, and define compatibility policy.

### Lead maintainer

The lead maintainer resolves decisions when consensus is not reached. The initial lead maintainer is Jordan García Morales (`xordanblu`).

## Decision process

Small changes use normal pull-request review.

A change needs a public design issue when it:

- changes the Patch Passport schema;
- changes default blocking behavior;
- adds a network service or hosted dependency;
- changes governance or licensing;
- removes a supported Python version;
- introduces telemetry.

Maintainers record the reason for consequential decisions. Security-sensitive details can remain private until publication is safe.

## Independence

No model provider, sponsor, or employer can silently change verification results. Sponsorship does not buy rule exceptions or maintainer approval.

## Conflict of interest

A maintainer should disclose a material conflict and avoid being the only approver for the affected decision.

## Project transfer

The project name, package, and repository should remain under a public-interest governance process. A transfer requires a public proposal, a 30-day comment period, and approval from two maintainers when two or more maintainers exist.
