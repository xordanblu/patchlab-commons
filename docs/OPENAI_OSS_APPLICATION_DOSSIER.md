# OpenAI open-source application dossier

> Internal preparation document. Do not submit it without a final human review. The evidence links below describe the public v0.2.0 release; adoption fields remain zero unless independently verified.

## Project identity

- Project: PatchLab Commons
- Repository: https://github.com/xordanblu/patchlab-commons
- Maintainer: Jordan García Morales (`xordanblu`)
- License: Apache-2.0
- Distribution: `patchlab-commons`
- Import package: `patchlab_commons`
- Command: `patchlab`
- Current version: `0.2.0` (alpha maturity)

## One-sentence description

PatchLab Commons compares a trusted base commit with a candidate commit, reviews new software capabilities, runs optional bounded verification, and creates a portable Patch Passport with verifiable evidence.

## Problem

Maintainers receive patches from people and coding agents. The author of a patch can also write its tests and its explanation. A normal diff does not prove that the defect existed before the patch, that the same reproduction passes afterward, or that the patch did not add dangerous permissions, network access, dependencies, secrets, or weaker tests.

PatchLab applies policy from a trusted revision. It records exact commits, static findings, command results, execution-boundary identity, reports, and SHA-256 digests. A maintainer keeps the final decision.

## Maintainer role

Jordan García Morales is the primary maintainer. The role includes:

- product direction;
- threat modeling;
- architecture;
- release management;
- issue triage;
- security response;
- documentation in English and Spanish;
- contributor review;
- community pilots;
- measurement and publication of honest adoption data.

## Defensive security boundary

PatchLab is a defensive review tool.

- Static mode does not execute candidate code.
- Linux container mode uses a non-root user, read-only root and source snapshot, removed capabilities, `no-new-privileges`, default-deny network access, and resource limits.
- Native mode is a weak boundary and requires explicit consent.
- The composite action protects its bootstrap from common Python module replacement.
- Git snapshots are materialized from tree and blob objects under a minimal Git environment.
- Final evidence is written and verified by the trusted coordinator.

PatchLab does not claim virtual-machine isolation, complete malware containment, program correctness, perfect secret detection, or automatic merge safety.

## How Codex is used

Current and planned uses:

- implement narrowly scoped features;
- generate and improve regression tests;
- compare base and candidate behavior;
- review pull requests against project policy;
- investigate CI failures;
- maintain bilingual documentation;
- prepare release notes;
- analyze static findings;
- help contributors understand a bounded laboratory without giving them hidden answers.

Every Codex-generated change remains subject to the same tests, policy, evidence, and human review as a human-authored change.

## Proposed use of API credits

API credits would support opt-in features, not the deterministic approval core:

1. Convert an incomplete issue into a proposed reproduction plan.
2. Explain Patch Passport findings in clear English or Spanish.
3. Suggest a minimal correction without applying it automatically.
4. Draft regression tests for maintainer review.
5. Classify maintenance issues and release notes.
6. Help build bilingual PatchLab learning laboratories.
7. Measure accepted suggestions, false positives, and maintainer time saved.

No API credit would be used to scan systems without permission, publish private vulnerabilities, fabricate users, or merge code without human approval.

## Program fit

### Codex for Open Source

PatchLab directly supports maintainers who review AI-assisted changes. Codex can help reproduce defects, write tests, explain evidence, and maintain the project. The deterministic verification core does not depend on one model.

### Codex Open Source Fund

Credits would fund opt-in issue-to-reproduction assistance, bilingual explanations, contributor guidance, and maintenance automation. Usage would be measured and bounded.

### Cybersecurity support

The project is defensive. It aims to reduce unsafe patch acceptance and to improve evidence for published or authorized fixes. Testing is limited to synthetic cases, project-owned systems, public vulnerabilities, or explicit authorization.

### Research access

A possible study can compare ordinary issue workflows with PatchLab-assisted workflows. Measures include completion, scope violations, test quality, review cycles, false positives, accepted fixes, and maintainer time.

## Short application text

### Project description

PatchLab Commons is an open-source CLI and GitHub Action that compares trusted base and candidate commits, detects risky capability changes, runs optional bounded verification, and creates a portable Patch Passport with exact commits, policy, results, and SHA-256 evidence.

### Why the repository matters

AI-assisted contributions are increasing the amount and speed of code review. PatchLab asks every patch to provide the same evidence, regardless of whether a person or agent wrote it. It helps maintainers reproduce defects, detect new powers, and retain final authority.

### Maintainer role

I am the primary maintainer. I own the roadmap, architecture, releases, issue triage, security response, documentation, community pilots, contributor review, and measurement of verified adoption.

### API credit use

Credits will support opt-in issue-to-reproduction assistance, bilingual explanations, test proposals, maintenance triage, and contributor laboratories. The deterministic approval core remains model-independent. All code changes and external actions require maintainer review.

## Evidence inventory

This table uses public workflow, release, and documentation endpoints rather than local claims. The workflow links expose the latest run and its job-level logs.

| Evidence | Status | Link or value |
|---|---|---|
| Public repository | PUBLISHED | https://github.com/xordanblu/patchlab-commons |
| Final commit | VERIFIED BY ANNOTATED RELEASE TAG | https://github.com/xordanblu/patchlab-commons/releases/tag/v0.2.0 |
| GitHub release | PUBLISHED FROM THE TAGGED COMMIT | https://github.com/xordanblu/patchlab-commons/releases/tag/v0.2.0 |
| CI matrix | VERIFIED ON PYTHON 3.11–3.14 ACROSS DECLARED HOSTS | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| Required CI check | VERIFIED | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| CodeQL | VERIFIED WITH `security-extended` QUERIES | https://github.com/xordanblu/patchlab-commons/actions/workflows/codeql.yml |
| Action module-hijack E2E | VERIFIED AS `Composite action resists Python module hijacking` | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| Linux container E2E | VERIFIED AS `Real Linux container isolation` | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| Pages | PUBLISHED | https://xordanblu.github.io/patchlab-commons/ |
| PyPI | NOT PUBLISHED; NOT REQUIRED FOR THE GITHUB RELEASE | — |
| Tests | 221 DISCOVERED TESTS | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| Combined line and branch coverage | 90.10%; 91.97% statements and 85.00% branches | https://github.com/xordanblu/patchlab-commons/actions/workflows/ci.yml |
| External repositories | 0 verified at preparation time | — |
| External contributors | 0 verified at preparation time | — |
| Upstream-accepted fixes using PatchLab | 0 verified at preparation time | — |
| Downloads | No claim | — |
| Stars | Do not use as proof of active use | — |

## Pilot plan

### Stage 1

- Recruit a small group from the Kodence community.
- Use synthetic and project-owned issues.
- Measure successful setup, completed Passports, and usability problems.

### Stage 2

- Invite maintainers of up to five external repositories.
- Require consent before creating automation or pull requests.
- Track findings confirmed useful and false positives.

### Stage 3

- Create bilingual contribution laboratories.
- Track completed laboratories, submitted patches, accepted patches, and review time.

## Metrics

- repositories with verified installations;
- real Patch Passports generated;
- accepted upstream patches;
- confirmed blocked risks;
- false-positive rate by rule;
- median review cycles;
- median maintainer time;
- contributors completing a laboratory;
- English and Spanish completion rates;
- API cost per completed maintenance task.

Synthetic demos must remain separate from adoption totals.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Overstating isolation | State exact container controls and kernel-sharing limit. |
| Treating AI output as approval | Keep deterministic policy and human authority. |
| Spam toward external repositories | Require maintainer consent and rate limits. |
| False positives | Record rule-level feedback and publish denominators. |
| Secret exposure | Default-deny environment and network; never use secrets in untrusted PR jobs. |
| Supply-chain compromise | Full action SHAs, OIDC release, artifact attestations, SBOM, and review. |
| Fake adoption | Count only verified external use and accepted work. |

## Submission gate

Do not submit until all applicable items are true:

- public repository contains the final history;
- final version tag is immutable;
- GitHub release exists;
- Required CI and CodeQL are green;
- E2E jobs are green;
- coverage is at least 90 percent;
- release assets and attestations verify;
- Pages works;
- repository security settings are recorded;
- the evidence table above contains real links;
- adoption fields use real numbers or explicitly say zero;
- the maintainer has reviewed the exact text.
