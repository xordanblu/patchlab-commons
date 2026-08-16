# Roadmap

The roadmap follows verified user need. A feature is complete only when it has tests, documentation, and a stated security boundary.

## 0.1 — evidence core

- [x] base-revision policy loading;
- [x] base and candidate Git snapshots;
- [x] command exit policies;
- [x] scope, workflow, dependency, secret, network, and test checks;
- [x] JSON, Markdown, and SARIF;
- [x] deterministic Patch Passport archives;
- [x] strict SHA-256 bundle verification;
- [x] bounded output paths and archive limits;
- [x] composite GitHub Action;
- [x] bilingual core documentation;
- [x] positive and blocked demonstrations.

## 0.2 — security hardening

- [x] direct Git tree and blob materialization;
- [x] hostile Git environment rejection;
- [x] Python module-hijack resistance in the composite action;
- [x] static execution as the default;
- [x] fail-closed Docker and Podman provider on Linux;
- [x] default-deny network mode;
- [x] non-root container user;
- [x] read-only root and source snapshot;
- [x] removed Linux capabilities and `no-new-privileges`;
- [x] CPU, memory, PID, time, output, and temporary-space limits;
- [x] explicit weak-native consent;
- [x] Python 3.11 through 3.14 matrix configuration;
- [x] reproducible-build checks, SBOM, and attestations in release automation;
- [x] hosted E2E definitions for action bootstrap and Linux isolation.

Hosted items above are configuration claims until the workflows run successfully in GitHub. See [`VALIDATION.md`](VALIDATION.md).

## 0.3 — maintainer experience

- [ ] pull-request annotations from SARIF without extra write permission;
- [ ] command-output attachments with independent digests;
- [ ] configuration migration command;
- [ ] richer dependency deltas for more ecosystems;
- [ ] stable schemas for every public object;
- [ ] rule suppression with owner, reason, and expiry;
- [ ] machine-readable false-positive feedback;
- [ ] monorepo presets.

## 0.4 — stronger isolation

- [ ] optional virtual-machine provider;
- [ ] rootless-container conformance suite;
- [ ] explicit artifact collection from isolated commands;
- [ ] disposable and content-addressed dependency cache policy;
- [ ] additional operating-system providers;
- [ ] published adversarial fixture corpus.

## 0.5 — PatchLab Commons laboratories

- [ ] `patchlab lab create` for a reproducible issue;
- [ ] maintainer and learner views;
- [ ] bounded hints without revealing hidden tests;
- [ ] Spanish and English laboratory metadata;
- [ ] Codespaces and local-container export;
- [ ] upstream contribution tracking with consent;
- [ ] accessibility review for learning interfaces.

## 0.6 — provenance and backports

- [ ] signed Patch Passports;
- [ ] Sigstore-compatible identity verification;
- [ ] protected-policy fingerprints;
- [ ] backport evidence linking;
- [ ] supported-branch correction ledger.

## Adoption milestones

- [ ] 5 external repositories;
- [ ] 10 external contributors;
- [ ] 20 verified real patches;
- [ ] 5 upstream-accepted fixes;
- [ ] documented false-positive measurements;
- [ ] first independent integration;
- [ ] first bilingual contributor cohort.

These are goals. They are not current adoption claims.
