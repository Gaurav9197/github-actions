# DevSecOps CI/CD Pipeline Documentation

Technical reference for the GitHub Actions pipeline defined in `.github/workflows/ci-cd.yml`.

---

## Table of Contents

- [Overview](#overview)
- [Triggers](#triggers)
- [Permissions](#permissions)
- [Pipeline Architecture](#pipeline-architecture)
- [Job Reference](#job-reference)
  - [code-quality](#code-quality)
  - [sast-scan](#sast-scan)
  - [secrets-scan](#secrets-scan)
  - [dependency-scan](#dependency-scan)
  - [dependency-review](#dependency-review)
  - [dockerfile-scan](#dockerfile-scan)
  - [pre-commit](#pre-commit)
  - [test](#test)
  - [docker-build](#docker-build)
  - [container-image-scan](#container-image-scan)
  - [docker-push](#docker-push)
  - [deploy](#deploy)
  - [security-report](#security-report)
- [Security Gates](#security-gates)
- [Reporting & Artifacts](#reporting--artifacts)
- [Caching Strategy](#caching-strategy)
- [Concurrency & Scheduling](#concurrency--scheduling)
- [Prerequisites](#prerequisites)
- [Troubleshooting](#troubleshooting)
- [Architecture Decisions](#architecture-decisions)

---

## Overview

The pipeline implements a DevSecOps workflow with 13 jobs spanning code quality, six categories of security scanning, multi-version testing, container build/scan/push, deployment with rollback, and consolidated security reporting.

**Tools used:**


| Category                 | Tool                     | Version/Action                         |
| ------------------------ | ------------------------ | -------------------------------------- |
| Linting & formatting     | Ruff                     | `ruff check`, `ruff format`            |
| Type checking            | mypy                     | `mypy .`                               |
| SAST                     | Semgrep                  | `semgrep/semgrep` container            |
| Secrets detection        | Gitleaks                 | `gitleaks/gitleaks-action@v2`          |
| Dependency scanning      | pip-audit                | `pip-audit` CLI                        |
| Dependency scanning      | Trivy (filesystem)       | `aquasecurity/trivy-action@0.35.0`     |
| Dependency review        | GitHub Dependency Review | `actions/dependency-review-action@v4`  |
| Dockerfile analysis      | Hadolint                 | `hadolint/hadolint-action@v3.1.0`      |
| Container image scanning | Trivy (image)            | `aquasecurity/trivy-action@0.35.0`     |
| SBOM generation          | Syft                     | `anchore/sbom-action@v0.23.0`          |
| Docker build             | Docker Buildx            | `docker/build-push-action@v6`          |
| Deployment               | SSH                      | `appleboy/ssh-action@v1`               |
| SARIF upload             | CodeQL                   | `github/codeql-action/upload-sarif@v3` |


---

## Triggers


| Trigger             | Condition                         | What Runs                                                                                          |
| ------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------- |
| `push`              | To `main` or `master` branch      | Full pipeline (quality + security + build + scan + push + deploy)                                  |
| `pull_request`      | Targeting `main` or `master`      | Quality + security + build + scan (no push, no deploy)                                             |
| `workflow_dispatch` | Manual trigger                    | Full pipeline                                                                                      |
| `schedule`          | `0 0 * * 0` (Sunday midnight UTC) | Security jobs only (code-quality, pre-commit, test, docker-build, docker-push, deploy are skipped) |


---

## Permissions

```yaml
permissions:
  contents: read          # Checkout code
  pull-requests: write    # Post security summary comment on PRs
  security-events: write  # Upload SARIF to GitHub Security tab
```

These are the minimum permissions required. The workflow follows the principle of least privilege.

---

## Pipeline Architecture

### Push / Pull Request Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Parallel Gate Jobs                            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ code-quality  │  │  sast-scan   │  │ secrets-scan │              │
│  │ (Ruff + mypy) │  │  (Semgrep)   │  │  (Gitleaks)  │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   test        │  │ dep-scan     │  │ dockerfile   │              │
│  │ (3.11-3.13)   │  │ (pip-audit   │  │   scan       │              │
│  │               │  │  + Trivy)    │  │ (Hadolint)   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                       │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │  pre-commit   │  │ dep-review   │                                │
│  │               │  │ (PR only)    │                                │
│  └──────┬───────┘  └──────┘───────┘                                │
└─────────┼──────────────────┼─────────────────────────────────────────┘
          │                  │
          ▼                  ▼
   ┌─────────────────────────────┐
   │       docker-build          │
   │  (Buildx → image.tar)      │
   └──────────┬──────────────────┘
              │
              ▼
   ┌─────────────────────────────┐
   │   container-image-scan      │
   │  (Trivy image + Syft SBOM) │
   └──────────┬──────────────────┘
              │
              ▼
   ┌─────────────────────────────┐
   │       docker-push           │  ← push events only
   │  (Load artifact → push)    │
   └──────────┬──────────────────┘
              │
              ▼
   ┌─────────────────────────────┐
   │         deploy              │  ← push events only
   │  (SSH → EC2, rollback)     │
   └─────────────────────────────┘

   ┌─────────────────────────────┐
   │     security-report         │  ← runs always (after all scans)
   │  (Summary + PR comment)    │
   └─────────────────────────────┘
```

### Scheduled (Weekly) Flow

Only security scan jobs run. All other jobs are skipped via `if: github.event_name != 'schedule'` conditions. The `docker-build` job is implicitly skipped because its dependencies (`code-quality`, `test`) are skipped.

```
schedule (Sunday midnight UTC)
    │
    ├── sast-scan         Semgrep
    ├── secrets-scan      Gitleaks
    ├── dependency-scan   pip-audit + Trivy
    ├── dockerfile-scan   Hadolint
    │
    └── security-report   Aggregated summary
```

---

## Job Reference

### code-quality


|                  |                           |
| ---------------- | ------------------------- |
| **Runs on**      | `ubuntu-latest`           |
| **Timeout**      | 10 minutes                |
| **Condition**    | Skipped on scheduled runs |
| **Dependencies** | None                      |


**Steps:**

1. Checkout code
2. Set up Python 3.13 with pip cache
3. Cache Ruff analysis data (keyed on config file hashes)
4. Install runtime + dev dependencies
5. **Ruff lint** -- checks for code issues, outputs GitHub-annotated warnings
6. **Ruff format** -- verifies code formatting
7. **mypy** -- static type checking with Flask type stubs

**Failure conditions:** Any lint error, formatting violation, or type error fails the job.

---

### sast-scan


|                  |                                                  |
| ---------------- | ------------------------------------------------ |
| **Runs on**      | `ubuntu-latest` (in `semgrep/semgrep` container) |
| **Timeout**      | 15 minutes                                       |
| **Condition**    | Runs on all events                               |
| **Dependencies** | None                                             |


**Steps:**

1. Checkout code
2. **Semgrep scan** with `auto` + `p/security-audit` rulesets, SARIF output, `--error` flag
3. Upload SARIF to GitHub Security tab (runs even on failure)
4. Upload SARIF as workflow artifact (30-day retention)

**What it detects:** Injection risks, insecure coding patterns, unsafe function usage, hardcoded credentials in source, OWASP Top 10 patterns.

**Failure conditions:** Any Semgrep finding fails the job (via `--error`).

---

### secrets-scan


|                  |                    |
| ---------------- | ------------------ |
| **Runs on**      | `ubuntu-latest`    |
| **Timeout**      | 10 minutes         |
| **Condition**    | Runs on all events |
| **Dependencies** | None               |


**Steps:**

1. Checkout code with full history (`fetch-depth: 0`)
2. **Gitleaks** official action scans all commits for secrets
3. Upload SARIF (`results.sarif`) to GitHub Security tab
4. Upload SARIF as workflow artifact (30-day retention)

**What it detects:** API keys, tokens, passwords, private keys, connection strings, and other credentials across the entire Git history.

**Failure conditions:** Any detected secret fails the job.

> **Note:** The official `gitleaks/gitleaks-action@v2` is free for public repositories. Private repositories require a `GITLEAKS_LICENSE` secret.

---

### dependency-scan


|                  |                    |
| ---------------- | ------------------ |
| **Runs on**      | `ubuntu-latest`    |
| **Timeout**      | 10 minutes         |
| **Condition**    | Runs on all events |
| **Dependencies** | None               |


**Steps:**

1. Checkout code
2. Set up Python 3.13 with pip cache
3. **Verify dependency integrity** -- warns if `requirements.txt` does not use `--hash` pinning
4. Install pip-audit
5. **pip-audit** -- scans `requirements.txt` against the PyPI advisory database (JSON report)
6. **Cache Trivy DB** -- restores vulnerability database from cache to avoid redundant downloads
7. **Trivy filesystem scan** -- scans the project directory for known CVEs in dependencies (SARIF output)
8. Upload Trivy SARIF to GitHub Security tab
9. Upload pip-audit JSON + Trivy SARIF as workflow artifacts (30-day retention)

**Why two scanners:** pip-audit focuses on Python-specific PyPI advisories. Trivy covers a broader vulnerability database (NVD, GitHub Advisories, etc.). Together they provide comprehensive coverage.

**Failure conditions:** Trivy exits with code 1 if CRITICAL or HIGH vulnerabilities are found. pip-audit runs with `|| true` to ensure Trivy always executes regardless of pip-audit results.

---

### dependency-review


|                  |                    |
| ---------------- | ------------------ |
| **Runs on**      | `ubuntu-latest`    |
| **Timeout**      | 10 minutes         |
| **Condition**    | Pull requests only |
| **Dependencies** | None               |


**Steps:**

1. Checkout code
2. **GitHub Dependency Review** -- diffs the dependency manifest against the base branch, flags new vulnerabilities introduced by the PR

**Failure conditions:** Fails if the PR introduces dependencies with known vulnerabilities.

---

### dockerfile-scan


|                  |                    |
| ---------------- | ------------------ |
| **Runs on**      | `ubuntu-latest`    |
| **Timeout**      | 10 minutes         |
| **Condition**    | Runs on all events |
| **Dependencies** | None               |


**Steps:**

1. Checkout code
2. **Hadolint** -- lints `Dockerfile` against best practices (SARIF output)
3. Upload SARIF to GitHub Security tab
4. Upload SARIF as workflow artifact (30-day retention)

**What it detects:** Missing version pinning in `apt-get install`, running as root, missing `HEALTHCHECK`, deprecated instructions, shell form vs. exec form issues, and other Dockerfile best practices.

**Failure conditions:** Fails on error-level findings (`failure-threshold: error`). Warnings and info-level findings are reported but do not block.

---

### pre-commit


|                  |                           |
| ---------------- | ------------------------- |
| **Runs on**      | `ubuntu-latest`           |
| **Timeout**      | 10 minutes                |
| **Condition**    | Skipped on scheduled runs |
| **Dependencies** | None                      |


**Steps:**

1. Checkout code
2. Set up Python 3.13 with pip cache
3. Cache pre-commit environments (keyed on `.pre-commit-config.yaml` hash)
4. Install pre-commit
5. Run all hooks on all files

**Hooks:** Ruff lint (auto-fix), Ruff format, trailing whitespace, end-of-file fixer, YAML/JSON validation, large file check, merge conflict detection, private key detection.

---

### test


|                  |                           |
| ---------------- | ------------------------- |
| **Runs on**      | `ubuntu-latest`           |
| **Timeout**      | 15 minutes                |
| **Condition**    | Skipped on scheduled runs |
| **Dependencies** | None                      |
| **Matrix**       | Python 3.11, 3.12, 3.13   |


**Steps:**

1. Checkout code
2. Set up Python (matrix version) with pip cache
3. Install runtime + dev dependencies
4. **Run tests** with coverage collection
5. **Enforce 80% coverage minimum** (`--fail-under=80`)
6. Generate XML coverage report
7. Upload to Codecov

**Failure conditions:** Any test failure or coverage below 80%.

---

### docker-build


|                  |                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------- |
| **Runs on**      | `ubuntu-latest`                                                                           |
| **Timeout**      | 15 minutes                                                                                |
| **Condition**    | Requires all gate jobs to pass                                                            |
| **Dependencies** | `code-quality`, `sast-scan`, `secrets-scan`, `dependency-scan`, `dockerfile-scan`, `test` |
| **Outputs**      | `image-ref` (first tag), `image-tags` (all tags, multi-line)                              |


**Steps:**

1. Checkout code
2. Set up Docker Buildx
3. Extract Docker metadata (generates tags: commit SHA, branch name, `latest` for default branch)
4. **Build image** using Buildx with GHA layer cache, export as `/tmp/image.tar`
5. Upload `image.tar` as workflow artifact (1-day retention)
6. Set image reference output

**Image tagging strategy:**

- `<sha>` -- commit SHA (always)
- `<branch>` -- branch name (always)
- `latest` -- only on default branch pushes

**This job does not push.** The image is exported as a tar archive for scanning first.

---

### container-image-scan


|                  |                       |
| ---------------- | --------------------- |
| **Runs on**      | `ubuntu-latest`       |
| **Timeout**      | 15 minutes            |
| **Condition**    | Requires docker-build |
| **Dependencies** | `docker-build`        |


**Steps:**

1. Download `image.tar` artifact
2. Load image into Docker daemon
3. **Cache Trivy DB** -- shares cache with `dependency-scan` job
4. **Trivy image scan (SARIF)** -- scans for CRITICAL/HIGH CVEs in OS packages and application dependencies
5. Upload SARIF to GitHub Security tab
6. **Trivy image scan (table)** -- human-readable output in workflow logs (CRITICAL/HIGH/MEDIUM)
7. **Generate SBOM** using Syft (CycloneDX JSON format), uploaded as artifact
8. Upload Trivy SARIF as workflow artifact (30-day retention)

**Failure conditions:** Trivy exits with code 1 if CRITICAL or HIGH vulnerabilities are found in the container image.

---

### docker-push


|                  |                                        |
| ---------------- | -------------------------------------- |
| **Runs on**      | `ubuntu-latest`                        |
| **Timeout**      | 10 minutes                             |
| **Condition**    | Push events only                       |
| **Dependencies** | `docker-build`, `container-image-scan` |


**Steps:**

1. Download `image.tar` artifact
2. Load image into Docker daemon
3. Log in to Docker Hub
4. **Push all tags** by iterating over `image-tags` output from `docker-build`

**Why load from artifact instead of rebuilding:** The image is loaded from the exact same tar archive that was scanned. This ensures zero divergence between what was scanned and what gets pushed. It also avoids checkout, Buildx setup, metadata recomputation, and rebuild overhead.

---

### deploy


|                  |                                                    |
| ---------------- | -------------------------------------------------- |
| **Runs on**      | `ubuntu-latest`                                    |
| **Timeout**      | 10 minutes                                         |
| **Condition**    | Push events only                                   |
| **Dependencies** | `docker-push`                                      |
| **Environment**  | `production` (URL: `http://<EC2_HOST>:5000`)       |
| **Concurrency**  | `deploy-production` group (cancels queued deploys) |


**Deployment sequence (via SSH to EC2):**

1. Log in to Docker Hub on the EC2 instance
2. Pull the latest image
3. Save the current container's image reference for rollback
4. Stop and remove the old container
5. Start a new container with Docker-native health checks (`--health-cmd`)
6. Poll Docker health status (up to 20 attempts, 3s apart)
7. **On success:** save deployment metadata to `/opt/deploy-backups/`, log out
8. **On failure:** dump container logs, stop the failed container, restart the previous image (rollback), log out, exit with error
9. **External health check** from the GitHub Actions runner -- verifies the deployment is reachable from outside the EC2 instance

**Rollback behavior:**

- If the new container fails health checks, the previous image is automatically restored.
- If no previous container existed, the job fails without rollback.
- Deployment metadata (full `docker inspect` output) is saved as a timestamped JSON file on each successful deploy.

---

### security-report


|                  |                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------- |
| **Runs on**      | `ubuntu-latest`                                                                           |
| **Timeout**      | 5 minutes                                                                                 |
| **Condition**    | Always runs (even if scans fail)                                                          |
| **Dependencies** | `sast-scan`, `secrets-scan`, `dependency-scan`, `dockerfile-scan`, `container-image-scan` |


**Steps:**

1. Download all scan artifacts
2. Parse each SARIF file and count findings
3. Generate a markdown summary table (`SECURITY_SUMMARY.md`)
4. Write summary to **GitHub Job Summary** (visible in Actions run page)
5. Upload summary as workflow artifact (30-day retention)
6. **On PRs:** Post (or update) a comment with the summary, using a marker to avoid duplicate comments

---

## Security Gates

The pipeline blocks progression at multiple points:


| Gate                | Tool               | Threshold         | Blocks              |
| ------------------- | ------------------ | ----------------- | ------------------- |
| SAST findings       | Semgrep            | Any finding       | `docker-build`      |
| Leaked secrets      | Gitleaks           | Any secret        | `docker-build`      |
| Dependency CVEs     | Trivy (filesystem) | CRITICAL or HIGH  | `docker-build`      |
| Dockerfile issues   | Hadolint           | Error-level       | `docker-build`      |
| Image CVEs          | Trivy (image)      | CRITICAL or HIGH  | `docker-push`       |
| New dependency CVEs | Dependency Review  | Any vulnerability | PR merge (advisory) |


**Build-scan-push flow:** The image is never pushed to Docker Hub until it passes the container scan. The sequence is strictly: **build** -> **scan** -> **push** -> **deploy**.

---

## Reporting & Artifacts

### SARIF Reports (GitHub Security Tab)

All scanners upload SARIF to the GitHub Security tab under dedicated categories:


| Category           | Scanner            | File                |
| ------------------ | ------------------ | ------------------- |
| `semgrep`          | Semgrep            | `semgrep.sarif`     |
| `gitleaks`         | Gitleaks           | `results.sarif`     |
| `trivy-dependency` | Trivy (filesystem) | `trivy-fs.sarif`    |
| `hadolint`         | Hadolint           | `hadolint.sarif`    |
| `trivy-image`      | Trivy (image)      | `trivy-image.sarif` |


View all findings at: **Repository > Security > Code scanning alerts**

### Workflow Artifacts


| Artifact Name             | Contents                                  | Retention |
| ------------------------- | ----------------------------------------- | --------- |
| `semgrep-report`          | `semgrep.sarif`                           | 30 days   |
| `gitleaks-report`         | `results.sarif`                           | 30 days   |
| `dependency-scan-reports` | `pip-audit-report.json`, `trivy-fs.sarif` | 30 days   |
| `hadolint-report`         | `hadolint.sarif`                          | 30 days   |
| `docker-image`            | `image.tar` (built Docker image)          | 1 day     |
| `container-scan-reports`  | `trivy-image.sarif`                       | 30 days   |
| `sbom-cyclonedx.json`     | CycloneDX SBOM (JSON)                     | Default   |
| `security-summary`        | `SECURITY_SUMMARY.md`                     | 30 days   |


### PR Comments

On pull requests, the `security-report` job posts (or updates) a comment with a findings summary table. The comment uses a hidden HTML marker (`<!-- security-summary -->`) to find and update itself on subsequent runs.

---

## Caching Strategy


| What                | Cache Key                      | Scope                                      | Saves                 |
| ------------------- | ------------------------------ | ------------------------------------------ | --------------------- |
| **pip packages**    | Dependency file hashes         | Per-job                                    | ~10-30s install time  |
| **Ruff analysis**   | Config file hashes             | `code-quality` job                         | ~2-5s analysis time   |
| **Pre-commit envs** | `.pre-commit-config.yaml` hash | `pre-commit` job                           | ~15-30s env setup     |
| **Docker layers**   | GitHub Actions cache (GHA)     | `docker-build` job                         | ~30-120s build time   |
| **Trivy vuln DB**   | `trivy-db-{os}-{run_id}`       | `dependency-scan` + `container-image-scan` | ~30-60s download time |


### Trivy DB Cache Details

- **Key pattern:** `trivy-db-Linux-<run_id>` (unique per run)
- **Restore key:** `trivy-db-Linux-` (falls back to most recent cache from any prior run)
- **Sharing:** The cache saved by `dependency-scan` is available to `container-image-scan` within the same workflow run (GitHub Actions shares caches across jobs)
- **Staleness:** Trivy checks if the cached DB is outdated and re-downloads if needed

---

## Concurrency & Scheduling

### Concurrency Control

Two concurrency groups prevent wasteful parallel runs:


| Group                  | Scope           | Behavior                                                                 |
| ---------------------- | --------------- | ------------------------------------------------------------------------ |
| `ci-${{ github.ref }}` | Entire workflow | Cancels in-progress runs for the same branch when a new commit is pushed |
| `deploy-production`    | Deploy job only | Cancels queued deployments so only the latest reaches production         |


### Scheduled Runs

The `schedule` trigger (`0 0 * * 0`) runs every Sunday at midnight UTC. Only security scan jobs execute:

- `sast-scan`, `secrets-scan`, `dependency-scan`, `dockerfile-scan` run normally
- `code-quality`, `pre-commit`, `test` are skipped (`if: github.event_name != 'schedule'`)
- `docker-build` is implicitly skipped (its dependencies are skipped)
- `docker-push` and `deploy` are skipped (they require `github.event_name == 'push'`)
- `security-report` runs and generates a weekly security summary

This catches newly disclosed vulnerabilities (new CVEs added to Trivy/pip-audit databases) without running unnecessary builds or deployments.

---

## Prerequisites

### GitHub Repository Configuration

**Secrets** (Settings > Secrets and variables > Actions > Secrets):


| Secret              | Purpose                                   |
| ------------------- | ----------------------------------------- |
| `DOCKERHUB_SECRETS` | Docker Hub access token                   |
| `CODECOV_TOKEN`     | Codecov upload token                      |
| `EC2_HOST`          | EC2 instance public IP or hostname        |
| `EC2_USER`          | SSH username (e.g., `ubuntu`, `ec2-user`) |
| `EC2_SSH_KEY`       | Private SSH key for the EC2 instance      |


**Variables** (Settings > Secrets and variables > Actions > Variables):


| Variable         | Purpose                                   |
| ---------------- | ----------------------------------------- |
| `DOCKERHUB_USER` | Docker Hub username (used in image names) |


**Automatic:**

- `GITHUB_TOKEN` is provided automatically by GitHub Actions

**Optional (private repos only):**

- `GITLEAKS_LICENSE` -- required for `gitleaks/gitleaks-action@v2` on private repositories

### GitHub Features


| Feature                  | Required For                           | Availability                                                        |
| ------------------------ | -------------------------------------- | ------------------------------------------------------------------- |
| GitHub Advanced Security | SARIF uploads to Security tab          | Free on public repos; paid on private repos                         |
| GitHub Environments      | `production` environment in deploy job | Free on public repos; paid on private repos (with protection rules) |


### EC2 Instance

- Docker installed and running
- SSH access open on port 22 (from [GitHub Actions IP ranges](https://api.github.com/meta))
- Port 5000 open in the security group
- SSH user has permission to run `docker` commands (member of `docker` group)
- `curl` installed (used by the health check inside the container)

### External Services


| Service                               | Setup                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| [Docker Hub](https://hub.docker.com/) | Create an account and generate an [access token](https://hub.docker.com/settings/security) |
| [Codecov](https://codecov.io/)        | Link your GitHub repository and copy the upload token                                      |


---

## Troubleshooting

### SARIF upload fails with 403

**Cause:** GitHub Advanced Security is not enabled for the repository (required for private repos).

**Fix:** Enable GitHub Advanced Security in Settings > Code security and analysis, or remove the `upload-sarif` steps if you don't need the Security tab integration.

### Gitleaks action fails with license error

**Cause:** `gitleaks/gitleaks-action@v2` requires a paid license for private repositories.

**Fix:** Add a `GITLEAKS_LICENSE` secret with your license key, or replace with manual Gitleaks CLI installation:

```yaml
- name: Install Gitleaks
  run: |
    curl -sSfL "https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_linux_x64.tar.gz" \
      | tar xz -C /usr/local/bin/
- name: Run Gitleaks
  run: gitleaks detect --source . --report-format sarif --report-path results.sarif -v
```

### Container scan finds vulnerabilities in base image

**Cause:** The `python:3.12-slim` base image contains OS packages with known CVEs.

**Fix options:**

1. Update the base image to the latest patch version
2. Switch to a minimal base image (e.g., `python:3.12-alpine`, distroless)
3. If the CVEs are not exploitable in your context, document the risk and adjust the severity filter in Trivy

### Deploy health check fails

**Cause:** The container starts but `/api/status` does not respond within 60 seconds (20 attempts x 3s).

**Debugging:**

1. Check the workflow logs for the container logs (last 50 lines are dumped on failure)
2. SSH into the EC2 instance and run `docker logs github-actions-dashboard`
3. Verify port 5000 is open in the security group
4. Check if the previous deployment rolled back successfully

### Docker push fails with "tag does not exist"

**Cause:** The `docker-build` job's `image-tags` output was not properly passed to `docker-push`.

**Debugging:**

1. Check the `docker-build` job's "Extract Docker metadata" step output
2. Verify the `image-tags` output is set in the "Set image reference output" step
3. Check the `docker-push` job's "Push all tags" step for the actual tag values

### Trivy DB download is slow

**Cause:** Cache miss (first run or cache expired).

**Expected behavior:** First run downloads the full DB (~200-400MB). Subsequent runs restore from cache and only download if the DB is stale. The cache is shared between `dependency-scan` and `container-image-scan` jobs.

### Scheduled run shows skipped jobs

**Expected behavior:** Scheduled runs intentionally skip `code-quality`, `pre-commit`, `test`, `docker-build`, `docker-push`, and `deploy`. Only security scan jobs run on schedule.

---

## Architecture Decisions

### Why build-scan-push instead of build-push-scan?

The image is built and exported as a tar artifact, scanned, and only pushed after the scan passes. This ensures vulnerable images are never pushed to Docker Hub. The tradeoff is a slightly longer pipeline (artifact upload/download), but the security benefit is significant.

### Why load from artifact instead of rebuilding in docker-push?

The `docker-push` job downloads and loads the exact tar archive that was scanned, rather than rebuilding from the GHA layer cache. This guarantees bit-for-bit identity between the scanned and pushed image, and avoids the overhead of checkout, Buildx setup, metadata recomputation, and cache-based rebuild.

### Why two dependency scanners (pip-audit + Trivy)?

pip-audit specializes in Python/PyPI advisories with high accuracy. Trivy covers a broader range of vulnerability databases (NVD, GitHub Advisories, Red Hat, etc.) and can catch issues pip-audit misses. The overlap provides defense in depth.

### Why Semgrep over Bandit for SAST?

Semgrep offers a broader rule ecosystem (auto config + community rulesets), supports SARIF natively, runs in a container (no Python dependency conflicts), and detects more vulnerability patterns beyond Python-specific issues.

### Why the official Gitleaks action over manual installation?

The `gitleaks/gitleaks-action@v2` handles binary management, version updates, and report generation automatically. It eliminates hardcoded version pinning and the risk of downloading from untrusted URLs. The tradeoff is that private repositories require a paid license.

### Why Trivy DB caching with run_id keys?

Using `trivy-db-{os}-{run_id}` as the cache key creates a unique entry per run, while `restore-keys: trivy-db-{os}-` falls back to the most recent cache. This ensures the cache is always updated (new key = new save) while still benefiting from prior downloads. Old cache entries are automatically evicted by GitHub's 10GB cache limit.

### Why separate docker-build and docker-push jobs?

Separating build and push into distinct jobs allows the container scan to run between them as a security gate. The `docker-push` job only executes if both `docker-build` and `container-image-scan` succeed, enforcing the build-scan-push flow at the job dependency level.
