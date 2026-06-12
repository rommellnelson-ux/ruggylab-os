# Dependency Management

This document describes how to manage and upgrade pinned dependencies in RuggyLab OS.

## Current Strategy

- Dependencies are pinned in `requirements.txt` to ensure reproducible builds.
- Automated updates are handled by Dependabot (weekly, limited to 5 open PRs).
- Security vulnerabilities are monitored via `pip-audit` in CI.

## Manual Upgrade Process

To upgrade a single dependency safely:

```bash
# 1. Update the requirement
pip install --upgrade <package-name>

# 2. Capture new version
pip freeze | grep <package-name> >> requirements.txt

# 3. Test locally
python -m pytest --tb=short -q

# 4. Check security
python -m pip_audit -r requirements.txt

# 5. Commit and push
git add requirements.txt
git commit -m "chore: upgrade <package-name> to <version>"
git push
```

## Reviewing Dependabot PRs

When Dependabot opens a PR:

1. Review the changelog for breaking changes.
2. Run local tests:
   ```bash
   git fetch origin
   git checkout origin/dependabot/...
   python -m pytest --tb=short -q
   ```
3. Approve and merge if tests pass.

## Pinned Versions

Key dependencies and their current versions:

- FastAPI: ~0.110.0
- SQLAlchemy: ~2.0
- Pydantic: ~2.0
- Pytest: ~9.0
- Ruff: ~0.15.0
- Python: 3.11, 3.12, 3.13

## Excluded Packages

Some packages are excluded from automatic updates:

- `torch` (ML, large binary, manual testing needed)
- Internal packages (local development)
