# Release process

## Preconditions

A release requires:

- a clean working tree;
- complete tests;
- coverage at or above the configured floor;
- both end-to-end demonstrations;
- valid YAML files;
- a clean wheel installation;
- updated `CHANGELOG.md`;
- matching versions in `_version.py`, `pyproject.toml`, and `CITATION.cff`;
- maintainer review of policy and workflows.

## Local validation

```bash
make clean
python -m pip install -e ".[dev]"
make compile
make coverage
python scripts/run_demo.py --output .patchlab/release-demo
python scripts/run_attack_demo.py --output .patchlab/release-blocked
patchlab verify-passport .patchlab/release-demo/patchlab-passport.tar.gz
patchlab verify-passport .patchlab/release-blocked/patchlab-passport.tar.gz
python -m build
```

Install the wheel into a clean environment and run:

```bash
patchlab --version
patchlab schema
```

## Git release

1. Commit the final release files.
2. Create a signed or annotated tag such as `v0.1.0`.
3. Push the commit and tag.
4. Wait for CI and CodeQL.
5. Create release notes from `CHANGELOG.md`.
6. Attach the source archive and wheel.
7. Record wheel and source SHA-256 values.

## Package publication

Use PyPI Trusted Publishing when the project is registered.

Do not store a long-lived PyPI token in repository secrets.

A publication workflow must have a separate protected environment and only the narrow `id-token: write` permission needed by Trusted Publishing.
