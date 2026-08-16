# Roadmap

The roadmap follows verified user need. A feature is complete only when it has tests, documentation, and a clear security boundary.

## 0.1 — functional evidence core

- [x] base and candidate Git worktrees;
- [x] base-revision policy loading;
- [x] command exit policies;
- [x] exact paths for spaces, renames, and binary files;
- [x] scope, capability, workflow, dependency, secret, and test checks;
- [x] JSON, Markdown, and SARIF;
- [x] deterministic Patch Passport archive profile;
- [x] strict SHA-256 bundle verification;
- [x] compressed and uncompressed archive limits;
- [x] safe output paths and symbolic-link rejection;
- [x] bounded command output;
- [x] common-secret output redaction;
- [x] process-group termination;
- [x] composite GitHub Action;
- [x] GitHub job summary;
- [x] pinned official actions in project workflows;
- [x] bilingual core documentation;
- [x] valid and blocked end-to-end demonstrations;
- [x] Linux, macOS, and Windows CI matrix.

## 0.2 — maintainer experience

- [ ] pull-request annotations from SARIF without extra write permission;
- [ ] command-output attachments with independent digests;
- [ ] configuration migration command;
- [ ] richer dependency deltas for more ecosystems;
- [ ] stable schemas for every public object;
- [ ] rule suppression with owner, reason, and expiry;
- [ ] machine-readable false-positive feedback;
- [ ] monorepo presets.

## 0.3 — stronger isolation

- [ ] Docker provider;
- [ ] Podman provider;
- [ ] default-deny network mode;
- [ ] read-only repository mounts;
- [ ] CPU, memory, process, and disk limits;
- [ ] explicit artifact collection;
- [ ] disposable dependency cache policy.

## 0.4 — PatchLab Commons laboratories

- [ ] `patchlab lab create` for a reproducible issue;
- [ ] maintainer and learner views;
- [ ] bounded hints without revealing hidden tests;
- [ ] Spanish and English laboratory metadata;
- [ ] Codespaces and local-container export;
- [ ] upstream contribution tracking with consent;
- [ ] accessibility review for learning interfaces.

## 0.5 — provenance and backports

- [ ] signed Patch Passports;
- [ ] Sigstore-compatible attestations;
- [ ] protected-policy fingerprints;
- [ ] reproducible build metadata;
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
