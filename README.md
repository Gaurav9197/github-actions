# GitHub Actions Dashboard

![CI/CD](https://github.com/<OWNER>/<REPO>/actions/workflows/ci-cd.yml/badge.svg)
[![codecov](https://codecov.io/gh/<OWNER>/<REPO>/branch/main/graph/badge.svg)](https://codecov.io/gh/<OWNER>/<REPO>)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)

A minimal Flask application with a production-grade DevSecOps CI/CD pipeline built on GitHub Actions. Integrates code quality, SAST, secrets detection, dependency scanning, Dockerfile analysis, container image scanning, SBOM generation, SARIF reporting, Docker Hub publishing, and automated EC2 deployment with rollback.

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
        └── ci-cd.yml               # DevSecOps CI/CD pipeline
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
```

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## CI/CD Pipeline

Everything runs in a single workflow (`ci-cd.yml`), triggered on push/PR to `main`/`master`, manual dispatch, and a weekly schedule (Sunday midnight UTC for security-only scans).

```
push / PR to main                          schedule (weekly)
    │                                           │
    ├── code-quality     Ruff + mypy            │ (skipped)
    ├── pre-commit       All hooks              │ (skipped)
    ├── test             Python 3.11/3.12/3.13  │ (skipped)
    ├── sast-scan        Semgrep ──────────────►├── sast-scan
    ├── secrets-scan     Gitleaks ─────────────►├── secrets-scan
    ├── dependency-scan  pip-audit + Trivy ────►├── dependency-scan
    ├── dockerfile-scan  Hadolint ─────────────►├── dockerfile-scan
    ├── dependency-review (PR only)             │
    │                                           │
    └── docker-build ──► container-image-scan   │ (skipped)
                              │                 │
                         docker-push            │
                              │                 │
                           deploy               │
                                                │
    security-report ◄───────────────────────────┘
```

### Pipeline Jobs

| Job | Tool(s) | Purpose |
|---|---|---|
| `code-quality` | Ruff, mypy | Linting, formatting, type checking |
| `sast-scan` | Semgrep | Static Application Security Testing (source code vulnerabilities) |
| `secrets-scan` | Gitleaks (official action) | Detects hardcoded credentials, API keys, tokens |
| `dependency-scan` | pip-audit, Trivy (filesystem) | Dependency vulnerability scanning (CVEs) |
| `dependency-review` | GitHub Dependency Review | PR-only diff review of new/changed dependencies |
| `dockerfile-scan` | Hadolint | Dockerfile best practices and misconfiguration analysis |
| `pre-commit` | pre-commit | All configured pre-commit hooks |
| `test` | unittest, coverage | Multi-version tests with 80% coverage gate |
| `docker-build` | Docker Buildx | Build image, export as artifact for scanning |
| `container-image-scan` | Trivy (image), Syft | Image vulnerability scan + SBOM generation (CycloneDX) |
| `docker-push` | Docker | Load scanned image from artifact, push to Docker Hub |
| `deploy` | SSH (appleboy) | Pull image on EC2, health check, auto-rollback |
| `security-report` | jq, github-script | Aggregate SARIF findings into summary, comment on PR |

### Security Gates

The pipeline enforces security gates that block progression on findings:

- **SAST**: Semgrep fails on any finding (`--error`)
- **Secrets**: Gitleaks fails on any detected secret
- **Dependencies**: Trivy fails on CRITICAL/HIGH CVEs (`exit-code: 1`)
- **Dockerfile**: Hadolint fails on error-level issues (`failure-threshold: error`)
- **Container image**: Trivy fails on CRITICAL/HIGH CVEs before push
- **Push-after-scan**: Docker image is only pushed to the registry after the container scan passes

### Reporting

| Output | Destination |
|---|---|
| SARIF reports (Semgrep, Gitleaks, Trivy, Hadolint) | GitHub Security tab + workflow artifacts |
| SBOM (CycloneDX JSON via Syft) | Workflow artifact |
| pip-audit JSON report | Workflow artifact |
| Security summary (markdown) | Job summary + PR comment + workflow artifact |

### Key Features

| Feature | Detail |
|---|---|
| **Code quality** | Ruff lint/format with GitHub annotations, mypy type checking |
| **SAST** | Semgrep with `auto` + `security-audit` rulesets |
| **Secrets detection** | Gitleaks official action with full history scan |
| **Dependency scanning** | pip-audit + Trivy filesystem scan, hash-pinning validation |
| **Dockerfile analysis** | Hadolint with SARIF output |
| **Container image scanning** | Trivy image scan (SARIF + table), fails on CRITICAL/HIGH |
| **SBOM generation** | Syft (CycloneDX JSON) for supply chain transparency |
| **SARIF integration** | All scanners upload to GitHub Security tab |
| **Security summary** | Aggregated report posted as PR comment and job summary |
| **Build-scan-push flow** | Image is built, scanned, then pushed (never pushes unscanned images) |
| **Multi-version testing** | Python 3.11, 3.12, 3.13 matrix |
| **Coverage enforcement** | Fails if coverage drops below 80% (Codecov integration) |
| **Docker Hub publishing** | Buildx with GHA layer caching, multi-tag (sha, branch, latest) |
| **Automated deployment** | SSH to EC2 with Docker-native health checks |
| **Auto-rollback** | Reverts to previous image if health check fails |
| **External health check** | Verifies deployment reachability from the runner |
| **Scheduled security scans** | Weekly cron runs security jobs only (skips tests/build/deploy) |
| **Trivy DB caching** | Vulnerability database cached across runs to avoid redundant downloads |
| **Concurrency control** | Auto-cancels duplicate CI runs and queued deploys |
| **Deployment environment** | GitHub environment (`production`) with URL and protection rules |
| **Deployment metadata** | Container inspect saved to `/opt/deploy-backups/` on each deploy |
| **Timeouts** | Every job has a timeout to prevent stuck runs |
| **Minimal permissions** | `contents: read`, `pull-requests: write`, `security-events: write` |
| **Caching** | pip, Ruff, pre-commit, Docker layers, and Trivy DB |

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

## Required Secrets & Variables

Configure these in your GitHub repository settings (**Settings > Secrets and variables > Actions**):

| Name | Type | Description |
|---|---|---|
| `DOCKERHUB_USER` | Variable | Docker Hub username |
| `DOCKERHUB_SECRETS` | Secret | Docker Hub access token |
| `CODECOV_TOKEN` | Secret | Codecov upload token |
| `EC2_HOST` | Secret | EC2 public IP or hostname |
| `EC2_USER` | Secret | SSH username (e.g., `ubuntu`, `ec2-user`) |
| `EC2_SSH_KEY` | Secret | Private SSH key for the EC2 instance |

`GITHUB_TOKEN` is provided automatically by GitHub Actions (used by Gitleaks, SARIF uploads, PR comments).

> **Note:** Gitleaks official action is free for public repositories. For private repositories, set a `GITLEAKS_LICENSE` secret (see [gitleaks-action docs](https://github.com/gitleaks/gitleaks-action)).

## API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard UI |
| `/api/status` | GET | Health check (returns JSON with `status` and `timestamp`) |

## License

[MIT](LICENSE)
