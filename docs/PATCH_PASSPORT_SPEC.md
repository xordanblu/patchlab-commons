# Patch Passport specification 1.1.0

## Purpose

A Patch Passport is a portable evidence package for one comparison between a base Git commit and a candidate Git commit.

It records checkable claims. It does not certify that software is safe or correct.

## Bundle members

A 1.1 bundle contains exactly four regular files:

- `report.json`
- `report.md`
- `results.sarif`
- `passport.json`

No directory, link, device, duplicate, unsafe path, or extra member is allowed.

The standard name is `patchlab-passport.tar.gz`.

## Report identity

`report.json` is the authoritative PatchLab result. It records:

- report schema version;
- tool version;
- project and repository identifiers;
- selected refs and exact commit IDs;
- generation time;
- trusted configuration source and SHA-256;
- execution mode and boundary;
- container runtime and image when used;
- network state;
- explicit native-risk acceptance;
- changed files, command results, findings, summary, and outcome.

Git object IDs can use 40 or 64 lowercase hexadecimal characters.

## Execution evidence

Each command result records:

- name and phase;
- argument array;
- required flag;
- expected exit policy;
- exit code;
- pass and timeout state;
- duration;
- bounded and redacted output;
- executor label;
- network state.

`static-no-execution` means no project command ran.

`isolated-container` means the selected command ran through the documented Linux container controls.

`weak-native` means the user explicitly accepted process hygiene without a security sandbox.

## Outcomes

- `pass`: no review or deny finding remains and all required dynamic evidence passes.
- `needs_review`: at least one review finding exists, no deny finding exists, and strict review failure is off.
- `fail`: a deny finding exists, a required command fails, or strict policy converts review into failure.

## Passport manifest

`passport.json` contains:

- schema version `1.1.0`;
- exact comparison identity;
- SHA-256 and byte size for each evidence file;
- serialization and verification metadata.

The 1.1 identity contains:

- `project`;
- `repository`;
- `base_sha`;
- `head_sha`;
- `outcome`;
- `generated_at`;
- `tool_version`;
- `config_source`;
- `config_sha256`;
- `execution_mode`;
- `execution_boundary`;
- `container_runtime`;
- `container_image`;
- `network_enabled`;
- `unsafe_native_accepted`.

The verifier retains read compatibility for schema 1.0.0 bundles.

## Deterministic archive profile

PatchLab normalizes:

- lexical member order;
- member and gzip timestamps to zero;
- user and group IDs to zero;
- blank user and group names;
- regular file mode to `0644`;
- UTF-8 JSON with sorted keys and stable indentation.

Repacking the same evidence bytes produces the same archive bytes.

## Verification

A verifier must:

1. enforce compressed and uncompressed limits;
2. reject unsafe paths, duplicate names, links, devices, directories, and extra members;
3. require the exact member set;
4. parse and validate the manifest structure and supported schema;
5. validate identity field types and values;
6. calculate SHA-256 from exact member bytes;
7. compare declared byte sizes;
8. confirm report and passport identities agree;
9. calculate the archive SHA-256 separately.

Machine-readable schemas are in `report.schema.json` and `passport.schema.json`.
