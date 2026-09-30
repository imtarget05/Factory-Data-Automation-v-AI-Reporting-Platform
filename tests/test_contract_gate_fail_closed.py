"""P0-03: a validation failure must never become data acceptance.

Root cause
----------
``apply_contract_gate`` wrapped the whole contract stage in::

    try:
        ...
    except Exception as exc:
        log_event(..., action="failing_open")
        return df                       # <-- the input frame, unchanged

The docstring called this deliberate: *"if the validator itself errors ... the
pipeline logs it and returns the frame unchanged rather than discarding a whole
file of good production data."*

That reasoning is sound for a **transient infrastructure** failure and wrong
for the case that actually matters. It conflates two states that must never be
confused:

* **business validation failure** -- a row breaks a contract rule. Correct
  response: record a violation, write the row to the quarantine DLQ, drop it,
  exclude it from KPI arithmetic. The rest of the file is still good.
* **validator implementation failure** -- the contract could not be evaluated
  at all (a pydantic upgrade changed an API, a contract bug, a bad import).
  Correct response: the rows are **unknown**, not approved. Accepting them
  means every downstream number (OEE, Yield, scrap rate) is computed over
  records that were never checked.

Measured before the fix: a row with ``Reject_Qty=9999`` survived a validator
that raised ``TypeError``, and 9999 reached the KPI layer. A gate that cannot
run is not a gate that passed.

The invariant this file enforces::

    VALIDATION_INFRA_FAILURE  MUST NOT  BECOME  DATA_ACCEPTANCE

Note what is deliberately *not* changed: an unknown dataset still skips
validation (there is no contract to apply), and genuine per-row violations
still quarantine rather than abort. Only the impossible-to-evaluate case
changes, and it fails the job.
"""
import numpy as np
import pandas as pd
import pytest

import app.data_contracts as DC
import app.etl.pipeline as pipeline
from app.etl.pipeline import ContractGateUnavailable, apply_contract_gate

GOOD_ROW = {
    "Date": "2026-01-01", "Line": "L1", "Shift": "S1", "Product": "P",
    "Machine_ID": "M1", "Worker_ID": "W1", "Target_Qty": 10,
    "Actual_Qty": 10, "Good_Qty": 9, "Reject_Qty": 1,
    "Cycle_Time_sec": 30.0, "Created_At": "2026-01-01 00:00:00",
}


def _frame(rows=None, **overrides):
    row = dict(GOOD_ROW)
    row.update(overrides)
    return pd.DataFrame(rows if rows is not None else [row])


def _boom(exc):
    def _raise(*_a, **_k):
        raise exc
    return _raise


# --- F6: the critical case. Validator implementation failure ---------------


@pytest.mark.parametrize("exc", [
    TypeError("simulated pydantic internal failure"),
    AttributeError("model_validate removed in this version"),
    ImportError("pydantic_core ABI mismatch"),
    RuntimeError("contract bug"),
])
def test_f6_validator_internal_exception_fails_closed(monkeypatch, exc):
    """A validator that cannot run must NOT accept rows.

    This is the case the old `except Exception: return df` silently converted
    into approval. Failing closed here means the caller sees an error, so the
    job stops and an operator looks -- the correct outcome for data that nobody
    has checked.

    The raised error must be a *domain* error, not the raw infrastructure
    exception: a caller that catches TypeError to mean "bad row data" would
    otherwise treat a contract bug as a data problem and skip the file.
    """
    monkeypatch.setattr(DC, "validate_rows", _boom(exc))
    df = _frame(Reject_Qty=9999)

    with pytest.raises(ContractGateUnavailable) as caught:
        apply_contract_gate(df, "production", "production.csv")

    assert isinstance(caught.value.__cause__, type(exc)), (
        "the original infrastructure exception must be preserved as __cause__ "
        "so the operator can see what actually broke"
    )
    assert type(exc).__name__ in str(caught.value), (
        "the domain error must name the underlying failure"
    )




# --- F1-F4: coercion failures must be VIOLATIONS, not exceptions ------------
#
# These already pass today and are kept as regression guards. They are the
# cases the original defect report described, and proving they were already
# correct is what isolates the real cause to the infra-failure path rather
# than to NaN handling.


@pytest.mark.parametrize("bad,label", [
    ("abc", "non-numeric string"),
    (float("nan"), "NaN"),
    (None, "None"),
    ("", "empty string"),
    (float("inf"), "+inf"),
    (float("-inf"), "-inf"),
])
def test_f1_to_f4_bad_values_are_quarantined_not_accepted(bad, label):
    """Every unusable value is a violation -> quarantined, never accepted."""
    df = _frame(Reject_Qty=bad)
    out = apply_contract_gate(df, "production", "production.csv")

    assert len(out) == 0, (
        f"{label} in a required integer field was ACCEPTED. A malformed record "
        f"in the KPI input is a data-correctness defect, not a rounding detail."
    )


def test_f3_none_nan_empty_abc_are_not_silently_equivalent():
    """F3: these must each be a violation, not collapsed into one 'blank'.

    They are distinguished here because they are distinguished upstream: the
    contract rejects all four, and the violation record preserves which one
    occurred. The point is that none of them may be *imputed* before the gate
    runs -- 'contracts REJECT, cleaning FILLS' is the invariant, and a
    median-fill applied first would turn 'abc' into a plausible-looking 5.0.
    """
    seen = {}
    for bad in ("abc", float("nan"), None, ""):
        df = _frame(Reject_Qty=bad)
        out = apply_contract_gate(df, "production", "production.csv")
        seen[repr(bad)] = len(out)

    assert set(seen.values()) == {0}, (
        f"every unusable value must be rejected; got {seen}"
    )


def test_f4_infinity_is_rejected_for_measure_fields():
    """inf would silently destroy a mean/sum; ge/le bounds must catch it."""
    df = _frame(Cycle_Time_sec=float("inf"))
    assert len(apply_contract_gate(df, "production", "production.csv")) == 0


# --- F5: mixed batch -- the numbers that actually matter -------------------


def test_f5_mixed_batch_partitions_with_zero_silent_loss(tmp_path):
    """100 valid + 3 invalid: 100 processed, 3 quarantined, 0 silent loss.

    This is the invariant the KPI layer depends on. A gate that drops 4 rows
    (one too many) or keeps 101 is worse than one that crashes, because the
    error is invisible downstream.
    """
    rows = []
    for i in range(100):
        r = dict(GOOD_ROW)
        r["Worker_ID"] = f"W{i}"
        r["Reject_Qty"] = i % 3          # 0..2, always <= Actual_Qty
        rows.append(r)
    for j, bad in enumerate(("abc", float("nan"), 999)):
        r = dict(GOOD_ROW)
        r["Worker_ID"] = f"BAD{j}"
        r["Reject_Qty"] = bad
        rows.append(r)

    df = pd.DataFrame(rows)
    assert len(df) == 103, "test setup: 103 input rows"

    qpath = tmp_path / "quarantine.csv"
    out = apply_contract_gate(df, "production", "production.csv",
                              quarantine_path=str(qpath))

    assert len(out) == 100, (
        f"expected 100 valid rows to survive, got {len(out)}. "
        f"in=103 out={len(out)} quarantined={103 - len(out)}"
    )
    assert not out["Reject_Qty"].isna().any(), "a NaN survived into the KPI frame"
    assert (out["Reject_Qty"] <= out["Actual_Qty"]).all(), "invariant violated"
    assert qpath.exists(), "rejected rows must be written to the quarantine DLQ"

    # The KPI layer must be able to compute on the survivors without NaN
    # propagation, which is the concrete harm P0-03 described.
    assert np.isfinite(out["Cycle_Time_sec"]).all()


# --- the invariant, stated directly ----------------------------------------


def test_invariant_validation_infra_failure_is_not_data_acceptance(monkeypatch):
    """VALIDATION_INFRA_FAILURE MUST NOT BECOME DATA_ACCEPTANCE."""
    monkeypatch.setattr(DC, "validate_rows", _boom(TypeError("contract bug")))
    df = _frame(Reject_Qty=9999)

    with pytest.raises(ContractGateUnavailable):
        apply_contract_gate(df, "production", "production.csv")


# --- negative controls -----------------------------------------------------


def test_nc_valid_rows_still_pass_the_gate():
    """The gate must not become fail-closed on everything."""
    df = pd.DataFrame([dict(GOOD_ROW, Worker_ID=f"W{i}", Reject_Qty=i % 3)
                       for i in range(20)])
    out = apply_contract_gate(df, "production", "production.csv")
    assert len(out) == 20, "valid data is being rejected -- over-correction"


def test_nc_genuine_violation_still_quarantines_rather_than_aborting():
    """A business validation failure must NOT raise.

    Failing the whole job on one bad row would be the opposite error: a single
    typo would discard a whole file of good production data, which is what the
    original fail-open comment was actually worried about. That concern is
    valid and is preserved.
    """
    df = _frame(Reject_Qty=999)   # Reject_Qty > Actual_Qty: a real violation
    out = apply_contract_gate(df, "production", "production.csv")
    assert len(out) == 0, "a contract violation must be quarantined, not raised"


def test_nc_unknown_dataset_still_skips_gracefully():
    """No contract for the dataset is a documented skip, not a crash."""
    df = _frame()
    out = apply_contract_gate(df, "no_such_dataset", "no_such_dataset.csv")
    assert len(out) == 1, "an unknown dataset must pass through unchanged"


def test_nc_loader_failure_still_reports_rather_than_raising():
    """A missing raw file is a different failure from a broken contract."""
    with pytest.raises(ValueError):
        DC.validate_csv("/nonexistent/file.csv", "production")

def test_f6b_infra_failure_does_not_return_rows(monkeypatch):
    """The frame must not come back at all -- returning it IS the defect."""
    monkeypatch.setattr(DC, "validate_rows", _boom(TypeError("boom")))
    df = _frame(Reject_Qty=9999)

    try:
        out = apply_contract_gate(df, "production", "production.csv")
    except Exception:
        out = None

    assert out is None, (
        "apply_contract_gate returned a frame after the validator raised. "
        "Those rows were never validated, so returning them is acceptance by "
        "default -- the exact P0-03 behaviour."
    )
