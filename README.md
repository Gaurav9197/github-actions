# GitHub Actions Dashboard

![CI](https://github.com/<OWNER>/<REPO>/actions/workflows/python-matrix.yml/badge.svg)
[![codecov](https://codecov.io/gh/<OWNER>/<REPO>/branch/main/graph/badge.svg)](https://codecov.io/gh/<OWNER>/<REPO>)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)

A minimal Flask application with a production-grade CI pipeline built on GitHub Actions. Demonstrates linting, type checking, security scanning, multi-version testing, dependency auditing, and Docker build verification -- all in a single workflow.

> **Replace `<OWNER>/<REPO>` in the badge URLs above with your GitHub username and repository name.**

## Project Structure

```
.
├── app.py                          # Flask application (routes: /, /api/status)
├── test_app.py                     # Unit tests
├── templates/
│   └── index.html                  # Dashboard UI
├── Dockerfile                      # Production image (gunicorn)
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Dev/CI dependencies (pinned)
├── .pre-commit-config.yaml         # Pre-commit hook configuration
└── .github/
    └── workflows/
        └── python-matrix.yml       # CI pipeline
```

## Quick Start

### Local Development

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python app.py
```

The app runs at `http://localhost:5000`.

### Docker

```bash
docker build -t github-actions-dashboard .
docker run -p 5000:5000 github-actions-dashboard
```

### Run Tests

```bash
coverage run -m unittest discover
coverage report
```

### Run Linters

```bash
ruff check .
ruff format --check .
mypy .
bandit -r . --skip B104
```

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## CI Pipeline

The workflow (`python-matrix.yml`) runs on every push/PR to `main`/`master` and consists of 6 jobs:

```
push / PR
    │
    ├── lint              Ruff lint + format, mypy, bandit
    ├── pre-commit        All pre-commit hooks
    ├── test              Unit tests across Python 3.11 / 3.12 / 3.13
    ├── dependency-scan   pip-audit against known vulnerabilities
    ├── dependency-review PR-only diff review of new dependencies
    │
    └── docker            Docker build test (runs after lint + test pass)
```

### Key Features

| Feature | Detail |
|---|---|
| **Linting & formatting** | Ruff with GitHub annotations |
| **Type checking** | mypy with Flask stubs |
| **Security scanning** | Bandit (SAST) + pip-audit (SCA) + dependency-review |
| **Multi-version testing** | Python 3.11, 3.12, 3.13 matrix |
| **Coverage enforcement** | Fails if coverage drops below 80% |
| **Coverage reporting** | Codecov with PR annotations |
| **Docker verification** | Buildx build with GHA layer caching |
| **Concurrency control** | Auto-cancels duplicate runs on the same branch |
| **Job gating** | Docker build only runs after lint + test pass |
| **Caching** | pip, Ruff, pre-commit, and Docker layer caches |
| **Timeouts** | Every job has a timeout to prevent stuck runs |
| **Minimal permissions** | `contents: read`, `pull-requests: write` only |
| **Pinned dependencies** | All actions and dev packages version-locked |

### Pre-commit Hooks

| Hook | Purpose |
|---|---|
| `ruff` | Lint with auto-fix |
| `ruff-format` | Code formatting |
| `trailing-whitespace` | Remove trailing whitespace |
| `end-of-file-fixer` | Ensure files end with newline |
| `check-yaml` | Validate YAML syntax |
| `check-json` | Validate JSON syntax |
| `check-added-large-files` | Block accidental large file commits |
| `check-merge-conflict` | Detect unresolved merge markers |
| `detect-private-key` | Prevent accidental key commits |

## API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard UI |
| `/api/status` | GET | Health check (returns JSON with `status` and `timestamp`) |

## License

[MIT](LICENSE)
