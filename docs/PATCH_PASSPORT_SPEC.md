# Patch Passport specification 1.0.0

## Purpose

A Patch Passport is a portable evidence package for one comparison between a base Git commit and a candidate Git commit.

It records claims that can be checked again. It does not certify that the software is safe or correct.

## Required bundle members

A version 1 bundle contains exactly these four regular files. No directory, link, device, duplicate, or extra member is allowed:

- `report.json`
- `report.md`
- `results.sarif`
- `passport.json`

The standard bundle name is `patchlab-passport.tar.gz`.

## `report.json`

`report.json` is the authoritative PatchLab result.

Required identity fields:

- `schema_version`
- `tool_version`
- `project_name`
- `generated_at`
- `repository`
- `base_ref`
- `base_sha`
- `head_ref`
- `head_sha`
- `outcome`

The two SHA fields contain full lowercase Git object IDs. Version 1 accepts SHA-1 identifiers with 40 hexadecimal characters and SHA-256 identifiers with 64 hexadecimal characters.

## Outcomes

### `pass`

No configured finding has `review` or `deny` disposition. All required commands satisfy their exit policy.

### `needs_review`

At least one finding has `review` disposition. No finding has `deny` disposition. Strict review failure is disabled.

### `fail`

At least one finding has `deny` disposition, a required command fails, or strict review failure converts a review finding into failure.

## Findings

Each finding contains:

- stable `rule_id`;
- title;
- message;
- severity;
- disposition;
- optional file and line;
- optional bounded evidence;
- optional recommendation;
- tags.

Severity describes presentation. Disposition controls the decision.

## Command results

Each result contains:

- command name;
- base or head phase;
- argument array;
- required flag;
- expected exit policy;
- actual exit code;
- pass flag;
- timeout flag;
- duration;
- bounded output.

Stored command output is bounded. PatchLab keeps the beginning and end when output is larger than the limit. It redacts several common credential forms.

Secrets must not be added to command output intentionally. Pattern redaction is not complete. Projects must prevent secret logging.

## `passport.json`

`passport.json` contains:

- schema version;
- an exact comparison identity;
- SHA-256 digest and byte size of each evidence file;
- digest input and serialization notes.

The identity contains exactly these fields:

- `project`;
- `repository`;
- `base_sha`;
- `head_sha`;
- `outcome`;
- `generated_at`;
- `tool_version`;
- `config_source`;
- `config_sha256`.

Artifact digests are calculated from raw file bytes. The manifest itself uses UTF-8 JSON with sorted keys and two-space indentation.

A verifier must calculate the digest from the exact bytes inside the archive.

## Deterministic archive profile

Version 1 uses:

- uncompressed tar metadata format: PAX;
- gzip compression;
- lexical member order;
- member timestamp `0`;
- gzip timestamp `0`;
- user ID `0`;
- group ID `0`;
- blank user and group names;
- regular file mode `0644`.

Generation time remains inside `report.json`. Therefore, two independently generated reports can differ when the recorded evidence differs. Repacking the same four files produces the same archive bytes.

## Verification

A verifier must:

1. enforce compressed and uncompressed limits;
2. reject non-regular members, duplicates, unsafe paths, and extra names;
3. require the exact version 1 member set;
4. validate the passport root, identity, verification metadata, digest syntax, and size types;
5. calculate SHA-256 from exact member bytes;
6. compare each declared byte size;
7. report every failed member;
8. calculate the archive SHA-256 separately.

## Compatibility

A breaking schema change requires a new major schema version.

Readers should ignore unknown metadata fields only when `additionalProperties` rules permit them. They must not reinterpret an unknown disposition as `allow`.

Machine-readable schemas are available in [`report.schema.json`](report.schema.json) and [`passport.schema.json`](passport.schema.json).
