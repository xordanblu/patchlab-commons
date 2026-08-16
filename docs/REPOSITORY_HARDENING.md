# Repository hardening checklist

Apply these settings after the first CI and CodeQL runs create their check names.

## General

- Public repository.
- Issues enabled.
- Discussions enabled.
- Wiki disabled.
- Delete merged branches enabled.
- Squash merge enabled.
- Rebase merge enabled.
- Merge commits disabled.

## Actions

- Default workflow token permission: read repository contents.
- Workflows cannot approve pull requests.
- Allow only reviewed actions.
- Keep external action references pinned to full SHAs.

## Security

- Dependency graph enabled.
- Dependabot alerts enabled.
- Dependabot security updates enabled.
- CodeQL default or advanced setup enabled through `codeql.yml`.
- Secret scanning enabled when the account supports it.
- Push protection enabled when the account supports it.
- Private vulnerability reporting enabled.

## `main` ruleset

- Changes require a pull request.
- Require `Required CI`.
- Require `CodeQL Python analysis`.
- Require resolved conversations.
- Dismiss stale approvals.
- Require approval after the latest push when a second reviewer exists.
- Require one approval when a second trusted reviewer exists.
- Require linear history.
- Block force pushes.
- Block deletion.
- Restrict bypass to documented emergency recovery.

A one-person repository cannot honestly require an independent approval without another trusted reviewer. Until one exists, require the pull-request flow, checks, conversations, and linear history. Record any administrative bypass in the pull request.

## Tag ruleset

Protect `refs/tags/v*` against update and deletion. A published tag is immutable.

## Release environment

Create environment `pypi`.

- Add a required reviewer when another maintainer exists.
- Register the exact workflow as a PyPI Trusted Publisher.
- Do not store a PyPI API token.
