# REPAIR PLAN — Factory-Data-Automation-v-AI-Reporting-Platform

Audit: 2026-09-25. The code was **cloned, installed and executed** on Windows.

---

## Current State

pandas + polars ETL over factory data, a FastAPI service, a Streamlit/Plotly/Altair dashboard, SQLAlchemy, reportlab PDF export, APScheduler, and ruff. One GitHub Actions workflow.

**The test suite fails on a fresh clone: 22 passed, 2 failed.**

---

## Broken Features

### B1 — The test suite depends on data the repository does not ship · **REPAIRED-eligible, HIGH VALUE**

`.gitignore` excludes the contents of the data directories:

```
data/raw/*
data/processed/*
data/exports/*
```

and negates only `.gitkeep`. So `data/raw/`, `data/processed/` and `data/exports/` each contain exactly one file: `.gitkeep`.

`tests/test_etl.py:22` and `:28` call `discover_files()` and assert that CSV files exist. On a fresh clone:

```
WARNING: No data files found in ...\data\raw
Available files: []
E   AssertionError: No CSV files found
E   assert 0 > 0
```

and

```
E   AssertionError: Missing: {'quality', 'inventory', 'machine', 'production', 'workers'}
```

`discover_files()` itself is correct — the log message it emits is accurate and helpful. The problem is that **no generator, fixture or seed script is committed**, so the tests can only pass on the machine of whoever wrote them, where the data already existed.

`scripts/` contains only `measure_time_saved.py`. There is no `generate_sample_data.py`.

**This is the highest repair-value-to-effort ratio in the whole portfolio: a deterministic generator turns 2 red tests green and makes the project cloneable by a reviewer in one command.**

Note that `faker>=20.0.0` is already a declared dependency in `requirements.txt`, so the intent to generate sample data clearly existed.

---

## Verified Working Features

Verified by execution: **22 tests pass.** Specifically:

- **ETL pipeline** — `app/etl/pipeline.py` cleans and transforms dataframes; `discover_files()` correctly enumerates and categorises source files.
- **Deduplication works** — `tests/test_etl.py` `TestCleanDataFrame::test_clean_removes_duplicates` passes, so the cleaning path is exercised for real.
- **Coherent dependency set** — `requirements.txt` installs cleanly on Python 3.11: pandas, polars, openpyxl, streamlit, plotly, fastapi, uvicorn, sqlalchemy, python-multipart, reportlab, faker, python-dotenv, apscheduler, httpx, altair, streamlit-aggrid.
- **ruff is configured** via `ruff.toml` and the package installs without a single dependency conflict.
- **CI workflow exists** (`.github/workflows/`) — `CI_IMPLEMENTED`.

---

## Half-implemented Features

None identified. The repository is small and internally consistent; its single failure mode is the missing data fixture. The `notebooks/` and `docs/` directories exist but were not part of the failing surface.

---

## Documentation Claims Not Verified

The README is 12 981 bytes and makes implementation-shaped claims. Without a full line-by-line read of every claim, the following are the ones that must be checked before this repo is shown to anyone, because the same class of error (README written from intent) has been found in six other repositories in this portfolio:

- Whether the claim "metrics saved / time saved" (`scripts/measure_time_saved.py`) is measured or estimated.
- Whether the claimed report formats are all actually produced by `app/`.
- Whether the APScheduler jobs in the README match `app/`'s scheduler configuration.

**Action: re-verify these against source before featuring the repo.** Do not assume.

---

## Security Problems

**No high-severity finding.** Specifically verified:

- No committed secrets. `.env` is gitignored; no `.env` is tracked.
- No authentication surface was found on the FastAPI routes — note that this repo is an internal analytics/reporting tool, so unauthenticated read endpoints are defensible, but it must be stated rather than assumed.
- No SQL string interpolation found in the SQLAlchemy usage.

**Recommendation:** add a note in the README that the service is intended for internal/trusted-network use and has no authentication. Saying so converts a liability into a documented scope decision.

---

## Testing Gaps

- **2 tests cannot pass on a fresh clone** (B1).
- **24 tests total** is a reasonable count for the size, and 22 of them assert real behaviour rather than importability.
- No test covers `scripts/measure_time_saved.py`.
- No test covers the FastAPI layer.
- No CI evidence was captured: `gh run list` was not consulted for this repository during the audit, so CI status is `NOT VERIFIED` — only "a workflow file exists".

---

## Deployment Gaps

- No `Dockerfile` and no `docker-compose.yml` at the root. There is a `docker/` directory, which was not deep-audited. The project cannot currently be demonstrated as a container.
- No deployment target of any kind. Cloud status: `NOT APPLICABLE` — this is an internal tool and cloud deployment is not a sensible goal for it.

---

## Recruiter-facing Problems

1. **`git clone && pytest` shows 2 failures.** For a data/analytics project whose credibility rests on the data pipeline, a reviewer cannot reproduce the tests. This is the entire problem with this repository, and it is a small one.
2. **No Docker and no demo command.** A portfolio reviewer needs a single command that shows the thing working. There isn't one.
3. **No `RECRUITER-EVIDENCE.md`.** The ETL and reporting pipeline is genuinely decent work with no artefact proving it.

---

## Repair Tasks

### P0 — blocking

- [ ] **P0-1 Add a deterministic sample-data generator.** Create `scripts/generate_sample_data.py` that writes the five expected CSVs (`production`, `quality`, `inventory`, `machine`, `workers`) into `data/raw/`, seeded and reproducible, using the already-declared `faker` dependency. Print the files it created. Wire it into the README's Local Development section and into CI as a step before `pytest` (mirroring what `ai-product-recommender` does correctly in `.github/workflows/ci.yml:37-40`).
- [ ] **P0-2 Add a `make setup` / `make test` target** so a reviewer has one command: install → generate data → run tests.
- [ ] **P0-3 Verify the suite is green from a clean clone.** Delete `data/raw/*` (except `.gitkeep`), run the generator, run `pytest`, confirm 24 passed.

### P1 — important

- [ ] **P1-1 Verify every README claim against source** and remove or downgrade anything not implemented. This repo has not had the same scrutiny as the larger projects and the portfolio-wide pattern predicts overstatement.
- [ ] **P1-2 Add a `Dockerfile`** for the FastAPI service and a `docker-compose.yml` with the service plus a Postgres instance, so the project is demonstrable as a container.
- [ ] **P1-3 Add a test for the FastAPI layer.** At minimum, one test that boots the app and asserts a health endpoint.
- [ ] **P1-4 Confirm the CI run status** with `gh run list --repo imtarget05/Factory-Data-Automation-v-AI-Reporting-Platform` and record the result. A workflow file is not evidence that it passes — this portfolio already contains three repos with green-looking workflows that do nothing.

### P2 — nice-to-have

- [ ] **P2-1** Document the intended deployment context (internal/trusted network, no auth) explicitly in the README.
- [ ] **P2-2** Add a test for `scripts/measure_time_saved.py`, or remove it if it is exploratory.
- [ ] **P2-3** Add `docs/RECRUITER-EVIDENCE.md` mapping each CV bullet → implementation file → test → runtime observation.
- [ ] **P2-4** Add screenshots of the Streamlit dashboard to the README so the value is visible without running anything.
