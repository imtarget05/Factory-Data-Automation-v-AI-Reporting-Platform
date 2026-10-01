"""Hygiene gate: Render must never be re-introduced as a deployment target.

ARCHITECTURE DECISION (repository cleanup):

    SOURCE -> GitHub Actions -> OIDC -> Terraform -> Azure Container Apps

Render is no longer a deployment target. This gate rejects ACTIVE deployment
artifacts (render.yaml blueprint, Render keepalive workflows, Render domains,
Render secret names) so the competing path cannot quietly come back.

WHAT IT DELIBERATELY DOES NOT DO: it does not ban the word "render". The
Streamlit dashboard renders pages (`app/dashboard/run.py`: "Render the Overview
page"), `app/data_contracts/validator.py` renders a quarantine DLQ row, and
ADR 0001 legitimately records why SQLite is the default on ephemeral free-tier
hosts. Only executable deployment artifacts are forbidden.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Directories that are never deployment artifacts and must not be crawled.
PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".kilo",
}

# A Render blueprint at any tracked location is an active deploy artifact.
FORBIDDEN_FILENAMES = ("render.yaml", "render.yml")

# Patterns that only ever mean "this deploys to / pings Render".
FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Render blueprint/domain URL", re.compile(r"\b(?:[a-z0-9-]+\.)*onrender\.com\b", re.I)),
    ("Render API domain", re.compile(r"\brender\.com\b", re.I)),
    ("Render secret/env reference", re.compile(r"\bRENDER_[A-Z0-9_]+\b")),
    ("Render deploy hook", re.compile(r"render[_-]?deploy[_-]?hook", re.I)),
)

# Explicit Render secret names that once wired this repo to Render.
RENDER_SECRETS = re.compile(
    r"\bRENDER_(?:API_KEY|SERVICE_ID|DEPLOY_HOOK|DEPLOY_HOOK_URL"
    r"|HEALTH_URL[A-Z_]*|API_BASE_URL)\b"
)


def _workflow_files() -> list[Path]:
    if not WORKFLOWS.is_dir():
        return []
    return sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})


def _hits(text: str) -> list[str]:
    return [label for label, rx in FORBIDDEN_PATTERNS if rx.search(text)]


def test_no_render_blueprint_file_exists():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*")
        if not (PRUNE_DIRS & set(p.parts)) and p.is_file() and p.name in FORBIDDEN_FILENAMES
    ]
    assert not offenders, (
        f"Render blueprint present — Render is not a deployment target: {offenders}"
    )


def test_no_workflow_deploys_or_pings_render():
    offenders: dict[str, list[str]] = {}
    for wf in _workflow_files():
        found = _hits(wf.read_text(encoding="utf-8", errors="replace"))
        if found:
            offenders[str(wf.relative_to(REPO_ROOT))] = found
    assert not offenders, (
        "Workflow(s) reference Render deploy/keepalive — the deploy story is "
        f"GitHub Actions -> OIDC -> Terraform -> Azure: {offenders}"
    )


def test_no_render_secret_names_referenced_by_workflows():
    offenders = [
        str(wf.relative_to(REPO_ROOT))
        for wf in _workflow_files()
        if RENDER_SECRETS.search(wf.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not offenders, f"Legacy Render secret refs in workflows: {offenders}"


def test_dashboard_and_dlq_render_helpers_still_exist():
    """Guard against over-cleaning: legitimate 'render' uses must survive.

    The Streamlit page renderers and the quarantine DLQ row renderer are not
    deployment artifacts. If these disappear the purge ate real code.
    """
    dashboard = REPO_ROOT / "app" / "dashboard" / "run.py"
    assert dashboard.is_file(), "dashboard render module missing — over-cleaned"
    text = dashboard.read_text(encoding="utf-8", errors="replace")
    assert "Render the Overview page" in text, "page renderers were removed"
    assert (REPO_ROOT / "app" / "data_contracts" / "validator.py").is_file()


def test_gate_is_not_vacuously_green():
    """The patterns must still match the real corpus they are written for."""
    workflows = _workflow_files()
    assert workflows, "no workflows found — gate would be vacuous"
    assert (WORKFLOWS / "ci.yml").is_file()
    # This file itself contains `onrender.com` inside a regex literal.
    assert _hits(Path(__file__).resolve().read_text(encoding="utf-8"))
