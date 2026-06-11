# Contributing

Thank you for contributing to RuggyLab OS. This document describes the main workflows for contributors.

Quick start
- Run the validation suite locally:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

- Install `pre-commit` and enable hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Commit messages
- Use conventional-style prefixes, e.g. `fix:`, `feat:`, `chore:`.

Running the full validation (Windows)
- Use the provided script:

```powershell
.\scripts\validate.ps1
```

Code style
- `ruff`, `black`, and `isort` are used. Please run them before committing or rely on `pre-commit`.

Security and tests
- All PRs should run the CI pipeline and include tests for new functionality.
