# WAVE 2 — CORE-0 source inventory + one blocking contradiction

> Lane B, worker `factory/core`, base `62a7a4a`. Read-only inspection; no
> application code has been modified yet. This file records what already exists
> so WAVE 2 extends it instead of duplicating it, and it records the one thing
> that must be decided before any code is written.

## What already exists (do not rebuild)

| Capability | Location | State |
|---|---|---|
| Run identity | `app/database/models.py::ETLRunManifest` | `run_id` **UNIQUE**, `started_at`, `completed_at`, `status`, `rows_ingested`, `rows_quarantined`, `checksum_sha256`, `error_message` |
| Quarantine | `app/database/models.py::QuarantineRecord` | `run_id`, `source_file`, `row_index`, `rejection_reason`, `raw_payload`, `quarantined_at` |
| Message dedup | `app/etl/servicebus_consumer.py::TelemetryConsumer.processed_ids` | **in-memory `set[str]` — a real gap, see below** |
| Batch + manifest | `TelemetryConsumer.process_batch` | writes `ETLRunManifest` with a sha256 over the batch |
| Row contracts | `app/data_contracts/validator.py` | fail-closed, quarantine-routing |
| Quality gate | `app/data_contracts/quality_gate.py::evaluate_quality` | deterministic, **never raises** (exception ⇒ `UNKNOWN`) |
| Report gate | `app/ai/reporting.py:240` | `if decision.status != GOOD:` ⇒ LLM is never invoked |
| Silver/Gold | `app/etl/medallion.py`, `gold.py`, `polars_etl.py` | present |
| KPI / mart | `app/etl/kpi_engine.py`, `app/database/marts.py` | present |
| Lineage | `app/catalog/lineage.py` | present |

Absent, and genuinely absent: `app/messaging/`, `app/storage/`, any migration
framework, any worker entry point, `StageExecution`, `QualityGateResult`,
`ReportManifest`.

## Gap 1 — dedup is process-local (real, must be fixed)

`TelemetryConsumer.processed_ids` is an in-memory `set`. WAVE 2 CORE-7 forbids
exactly this, and correctly:

- two worker replicas each have their own set, so a duplicate delivered to
  replica A then replica B is processed **twice**
- a restart empties the set, so every in-window message is re-processable
- there is no durable record tying a stage to a semantic key

The fix is a DB unique constraint on `(run_id, stage)`, not a bigger cache.

## Gap 2 — `run_id` is batch-scoped, not stage-scoped

`process_batch` derives `run-{YYYYMMDDHHMMSS}`, so two batches in the same
second collide on the `run_id` UNIQUE constraint and the second raises
`IntegrityError`, which `_record_manifest` then swallows into a `logger.warning`.
That is a silent data-loss path, not a crash.

WAVE 2 CORE-1 wants `(run_id, stage)` as the semantic key, which needs a
separate `StageExecution` table — it does not fit the current one-row-per-run
manifest shape.

## BLOCKING CONTRADICTION — quality vocabulary

The WAVE 2 specification (CORE-18) asks the gate to output
`GOOD | WARNING | CRITICAL`.

The shipped, tested, mutation-controlled gate outputs **`GOOD | BAD | UNKNOWN`**
(`app/data_contracts/quality_gate.py:30-32`), and its block rule is
`decision.status != GOOD` (`app/ai/reporting.py:240-241`).

These are not the same design:

| | Shipped | Spec (CORE-18/20) |
|---|---|---|
| states | `GOOD`, `BAD`, `UNKNOWN` | `GOOD`, `WARNING`, `CRITICAL` |
| meaning of the middle state | none — every non-GOOD blocks | `WARNING` is presumably non-blocking |
| unknown gate outcome | its own state, blocks | no equivalent; an `UNKNOWN` would have to be forced into `WARNING` or `CRITICAL` |
| block rule | `!= GOOD` | `== CRITICAL` blocks |

Three consequences, and this is why it needs a decision rather than a rename:

1. **`WARNING` is a genuinely new state**, not a relabelling. It introduces a
   non-blocking middle outcome, which needs its own policy for *what a WARNING
   report is allowed to claim*. That is a business decision.
2. **`UNKNOWN` would be lost.** Today an exception inside the gate yields
   `UNKNOWN`, which blocks. Under the spec's vocabulary it would have to become
   `CRITICAL`, which is a *stronger* claim than the evidence supports — the gate
   did not measure bad data, it failed to measure at all. Collapsing them loses
   the distinction between "measured: bad" and "could not measure".
3. **The block rule changes shape.** `!= GOOD` (deny by default) becomes
   `== CRITICAL` (allow by default unless one specific value). That is a
   materially weaker posture, and it is a change to the repository's central
   safety invariant.

Renaming would also invalidate the existing evidence: 19 gate regression tests
plus **4 xfailed mutation controls that must never pass**
(`tests/test_ai_quality_mutations.py`). A mutation control that starts failing
is not a nuisance — it means the control no longer detects its mutation.

### Requested decision

**Option A — keep `GOOD | BAD | UNKNOWN`, add a separate severity axis.**
`status` stays the trust decision (`GOOD` / `BLOCKED`); a new orthogonal
`severity` field carries `WARNING` / `CRITICAL` for presentation and alerting.
The deny-by-default posture and all four mutation controls survive untouched.

**Option B — adopt the spec vocabulary and widen the evidence.**
`GOOD | WARNING | CRITICAL | UNKNOWN`, block on anything that is not `GOOD`,
and update the 19 tests plus the 4 mutation controls together. Larger blast
radius, and the mutation controls must be re-proven after the rename.

**Option C — adopt `GOOD | WARNING | CRITICAL` and drop `UNKNOWN`.**
Not recommended: an unmeasurable gate would be reported as `CRITICAL`, which is
a claim about the data that the gate has no evidence for.

No code will be written until this is decided, because every model, every test
and the `CORE-20` CRITICAL invariant depend on the answer.
