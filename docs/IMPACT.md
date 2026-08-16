# Impact and measurement

PatchLab Commons must be judged by verified use, not by repository volume or promotional metrics.

## Current baseline

At the `0.2.0` release-preparation stage, no external adoption number is claimed.

Synthetic demonstrations, local test runs, repository stars, and automated downloads are not counted as users or accepted patches.

## Primary measures

- external repositories that run PatchLab on real changes;
- Patch Passports generated for real reviews;
- patches accepted upstream;
- unsafe changes blocked before merge;
- findings confirmed as useful by maintainers;
- false-positive rate per rule;
- median maintainer review time;
- new contributors who complete a patch laboratory.

## Evidence rules

Public impact reports must:

- distinguish attempted, completed, submitted, accepted, and merged patches;
- exclude synthetic demo runs from adoption totals;
- identify the measurement period and data source;
- document missing or partial data;
- preserve user and security privacy;
- avoid purchased stars, fake downloads, false testimonials, or automated contribution spam.

## Pilot design

A first pilot can compare two contribution flows:

1. a normal public issue;
2. the same class of issue with a PatchLab reproduction and Passport requirement.

Measure completion, test quality, scope violations, review cycles, maintainer time, false positives, and accepted fixes.

A result should include the raw denominator. For example, report “3 accepted of 12 submitted” instead of only “3 accepted fixes.”
