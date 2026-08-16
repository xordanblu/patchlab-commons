from __future__ import annotations

from typing import Any


def _common_defs() -> dict[str, Any]:
    return {
        "gitSha": {
            "type": "string",
            "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$",
        },
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    }


def report_schema() -> dict[str, Any]:
    nullable_string = {"type": ["string", "null"]}
    nullable_integer = {"type": ["integer", "null"]}
    definitions = _common_defs()
    definitions.update(
        {
            "summary": {
                "type": "object",
                "required": [
                    "changed_files",
                    "commands",
                    "commands_passed",
                    "findings",
                    "blocking_findings",
                    "review_findings",
                ],
                "properties": {
                    "changed_files": {"type": "integer", "minimum": 0},
                    "commands": {"type": "integer", "minimum": 0},
                    "commands_passed": {"type": "integer", "minimum": 0},
                    "findings": {"type": "integer", "minimum": 0},
                    "blocking_findings": {"type": "integer", "minimum": 0},
                    "review_findings": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            "changedFile": {
                "type": "object",
                "required": [
                    "status",
                    "path",
                    "old_path",
                    "added_lines",
                    "deleted_lines",
                    "binary",
                ],
                "properties": {
                    "status": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "old_path": nullable_string,
                    "added_lines": nullable_integer,
                    "deleted_lines": nullable_integer,
                    "binary": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "commandResult": {
                "type": "object",
                "required": [
                    "name",
                    "phase",
                    "command",
                    "required",
                    "expected_exit",
                    "exit_code",
                    "passed",
                    "timed_out",
                    "duration_seconds",
                    "stdout",
                    "stderr",
                    "executor",
                    "network_enabled",
                ],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "phase": {"enum": ["base", "head"]},
                    "command": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "required": {"type": "boolean"},
                    "expected_exit": {"enum": ["zero", "nonzero", "base_nonzero_head_zero"]},
                    "exit_code": nullable_integer,
                    "passed": {"type": "boolean"},
                    "timed_out": {"type": "boolean"},
                    "duration_seconds": {"type": "number", "minimum": 0},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "executor": {"type": "string", "minLength": 1},
                    "network_enabled": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "finding": {
                "type": "object",
                "required": [
                    "rule_id",
                    "title",
                    "message",
                    "severity",
                    "disposition",
                    "file",
                    "line",
                    "evidence",
                    "recommendation",
                    "tags",
                ],
                "properties": {
                    "rule_id": {
                        "type": "string",
                        "pattern": "^PL-[A-Z]+-[0-9]{3}$",
                    },
                    "title": {"type": "string", "minLength": 1},
                    "message": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["info", "warning", "error"]},
                    "disposition": {"enum": ["allow", "review", "deny"]},
                    "file": nullable_string,
                    "line": nullable_integer,
                    "evidence": nullable_string,
                    "recommendation": nullable_string,
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "additionalProperties": False,
            },
            "commitMetadata": {
                "type": "object",
                "required": [
                    "commit",
                    "tree",
                    "authored_at",
                    "author_name",
                    "subject",
                ],
                "properties": {
                    "commit": {"$ref": "#/$defs/gitSha"},
                    "tree": {"$ref": "#/$defs/gitSha"},
                    "authored_at": {"type": "string", "format": "date-time"},
                    "author_name": {"type": "string"},
                    "subject": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "metadata": {
                "type": "object",
                "required": [
                    "platform",
                    "python",
                    "base_commit",
                    "head_commit",
                    "human_review_required",
                    "fail_on_review",
                    "environment",
                    "config_source",
                    "config_location",
                    "config_sha256",
                    "execution_mode",
                    "execution_boundary",
                    "container_runtime",
                    "container_image",
                    "network_enabled",
                    "unsafe_native_accepted",
                ],
                "properties": {
                    "platform": {"type": "string"},
                    "python": {"type": "string", "minLength": 1},
                    "base_commit": {"$ref": "#/$defs/commitMetadata"},
                    "head_commit": {"$ref": "#/$defs/commitMetadata"},
                    "human_review_required": {"type": "boolean"},
                    "fail_on_review": {"type": "boolean"},
                    "environment": {"enum": ["local", "github-actions"]},
                    "config_source": {"enum": ["base", "head", "working-tree"]},
                    "config_location": {"type": "string", "minLength": 1},
                    "config_sha256": {"$ref": "#/$defs/sha256"},
                    "execution_mode": {"enum": ["static", "native", "container"]},
                    "execution_boundary": {
                        "enum": [
                            "static-no-execution",
                            "weak-native",
                            "isolated-container",
                        ]
                    },
                    "container_runtime": {"type": "string"},
                    "container_image": {"type": "string"},
                    "network_enabled": {"type": "boolean"},
                    "unsafe_native_accepted": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://raw.githubusercontent.com/xordanblu/patchlab-commons/"
            "v0.2.0/docs/report.schema.json"
        ),
        "title": "PatchLab Patch Passport Report",
        "description": "Machine-readable evidence for one base-to-candidate Git comparison.",
        "type": "object",
        "required": [
            "schema_version",
            "tool_version",
            "project_name",
            "generated_at",
            "repository",
            "base_ref",
            "base_sha",
            "head_ref",
            "head_sha",
            "outcome",
            "summary",
            "changed_files",
            "command_results",
            "findings",
            "metadata",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.1.0"},
            "tool_version": {"type": "string", "minLength": 1},
            "project_name": {"type": "string", "minLength": 1},
            "generated_at": {"type": "string", "format": "date-time"},
            "repository": {"type": "string", "minLength": 1},
            "base_ref": {"type": "string", "minLength": 1},
            "base_sha": {"$ref": "#/$defs/gitSha"},
            "head_ref": {"type": "string", "minLength": 1},
            "head_sha": {"$ref": "#/$defs/gitSha"},
            "outcome": {"enum": ["pass", "needs_review", "fail"]},
            "summary": {"$ref": "#/$defs/summary"},
            "changed_files": {
                "type": "array",
                "items": {"$ref": "#/$defs/changedFile"},
            },
            "command_results": {
                "type": "array",
                "items": {"$ref": "#/$defs/commandResult"},
            },
            "findings": {
                "type": "array",
                "items": {"$ref": "#/$defs/finding"},
            },
            "metadata": {"$ref": "#/$defs/metadata"},
        },
        "$defs": definitions,
        "additionalProperties": False,
    }


def passport_schema() -> dict[str, Any]:
    definitions = _common_defs()
    definitions.update(
        {
            "artifact": {
                "type": "object",
                "required": ["sha256", "size"],
                "properties": {
                    "sha256": {"$ref": "#/$defs/sha256"},
                    "size": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 33_554_432,
                    },
                },
                "additionalProperties": False,
            },
            "identity": {
                "type": "object",
                "required": [
                    "project",
                    "repository",
                    "base_sha",
                    "head_sha",
                    "outcome",
                    "generated_at",
                    "tool_version",
                    "config_source",
                    "config_sha256",
                    "execution_mode",
                    "execution_boundary",
                    "container_runtime",
                    "container_image",
                    "network_enabled",
                    "unsafe_native_accepted",
                ],
                "properties": {
                    "project": {"type": "string", "minLength": 1},
                    "repository": {"type": "string", "minLength": 1},
                    "base_sha": {"$ref": "#/$defs/gitSha"},
                    "head_sha": {"$ref": "#/$defs/gitSha"},
                    "outcome": {"enum": ["pass", "needs_review", "fail"]},
                    "generated_at": {"type": "string", "format": "date-time"},
                    "tool_version": {"type": "string", "minLength": 1},
                    "config_source": {"enum": ["base", "head", "working-tree"]},
                    "config_sha256": {"$ref": "#/$defs/sha256"},
                    "execution_mode": {"enum": ["static", "native", "container"]},
                    "execution_boundary": {
                        "enum": [
                            "static-no-execution",
                            "weak-native",
                            "isolated-container",
                        ]
                    },
                    "container_runtime": {"type": "string"},
                    "container_image": {"type": "string"},
                    "network_enabled": {"type": "boolean"},
                    "unsafe_native_accepted": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://raw.githubusercontent.com/xordanblu/patchlab-commons/"
            "v0.2.0/docs/passport.schema.json"
        ),
        "title": "PatchLab Patch Passport Manifest",
        "description": "Digest manifest and identity for a Patch Passport bundle.",
        "type": "object",
        "required": ["schema_version", "identity", "artifacts", "verification"],
        "properties": {
            "schema_version": {"type": "string", "const": "1.1.0"},
            "identity": {"$ref": "#/$defs/identity"},
            "artifacts": {
                "type": "object",
                "required": ["report.json", "report.md", "results.sarif"],
                "properties": {
                    "report.json": {"$ref": "#/$defs/artifact"},
                    "report.md": {"$ref": "#/$defs/artifact"},
                    "results.sarif": {"$ref": "#/$defs/artifact"},
                },
                "additionalProperties": False,
            },
            "verification": {
                "type": "object",
                "required": [
                    "algorithm",
                    "artifact_input",
                    "manifest_serialization",
                ],
                "properties": {
                    "algorithm": {"const": "sha256"},
                    "artifact_input": {"const": "raw file bytes"},
                    "manifest_serialization": {
                        "const": "UTF-8 JSON, sorted keys, 2-space indentation"
                    },
                },
                "additionalProperties": False,
            },
        },
        "$defs": definitions,
        "additionalProperties": False,
    }
