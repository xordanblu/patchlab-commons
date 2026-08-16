# Patch Passport

✅ **Outcome: `pass`**

## Identity

| Field | Value |
|---|---|
| Project | `patchlab-demo-calculator` |
| Repository | `https://github.com/patchlab/examples.git` |
| Base | `80595bd0b691cbf7d486d5cf3f9efd7d2d965869` → `80595bd0b691cbf7d486d5cf3f9efd7d2d965869` |
| Head | `6c7e18d0a57caf878a8e5b80f8ff889b3b2f7105` → `6c7e18d0a57caf878a8e5b80f8ff889b3b2f7105` |
| Generated | `2026-08-16T15:05:57Z` |
| PatchLab | `0.1.0` |

## Summary

| Metric | Count |
|---|---:|
| Changed files | 1 |
| Commands | 3 |
| Passed commands | 3 |
| Findings | 0 |
| Blocking findings | 0 |
| Review findings | 0 |

## Command evidence

| Command | Phase | Expected | Exit | Result | Duration |
|---|---|---|---:|---|---:|
| `reproduce-addition-bug` | `base` | `base_nonzero_head_zero` | 1 | **PASS** | 0.718s |
| `reproduce-addition-bug` | `head` | `base_nonzero_head_zero` | 0 | **PASS** | 0.666s |
| `full-test-suite` | `head` | `zero` | 0 | **PASS** | 0.668s |

## Policy findings

No policy findings.

## Changed files

| Status | File | Added | Deleted |
|---|---|---:|---:|
| `M` | `calculator.py` | 1 | 1 |

---

This passport records reproducible evidence. It does not replace human review.
