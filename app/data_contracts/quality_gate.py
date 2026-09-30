"""Dataset-level quality gate — deterministic authorization for AI reporting.

Two distinct trust boundaries exist in this repo:

1. Row-level contracts (:mod:`app.data_contracts.validator`) decide which raw
   rows may enter the business layer. Violating rows go to quarantine.
2. THIS gate decides whether the *current business snapshot* may be handed to
   AI reporting at all.

The LLM never decides either question: "Data quality authorizes AI
reporting; the LLM never decides whether the source data is trustworthy."

Status semantics (fail closed):

    GOOD      all blocking checks passed -> reporting may proceed
    BAD       at least one check failed  -> reporting BLOCKED
    UNKNOWN   the gate itself could not run -> reporting BLOCKED
                                             (never silently GOOD)

Checks are deliberately simple and deterministic — no SLO platform: the
invariant that matters is that a BAD/UNKNOWN decision can never reach the
report generator as trusted input.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

GOOD = "GOOD"
BAD = "BAD"
UNKNOWN = "UNKNOWN"

REQUIRED_DATASETS = ("production", "quality", "machine", "inventory")
REQUIRED_KPIS = ("daily_production", "oee")

# More than half the source rows rejected => the snapshot is not reportable.
# Quarantine itself is normal (a few bad rows); this bound only fires when
# the DLQ swallowed the majority of the input.
QUARANTINE_RATE_MAX = 0.5


@dataclass
class QualityDecision:
    """Deterministic outcome of evaluating a business snapshot."""

    status: str
    checks: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    source: dict = field(default_factory=dict)
    period: dict = field(default_factory=dict)
    # Wall-clock audit stamp. Deliberately named so nobody mistakes it for
    # deterministic content: every other field is a pure function of the inputs.
    evaluated_at_epoch: float = field(default_factory=time.time)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checks": list(self.checks),
            "failures": list(self.failures),
            "source": dict(self.source),
            "period": dict(self.period),
            "evaluated_at_epoch": self.evaluated_at_epoch,
            "reason": self.reason,
        }


def _finite_check(kpis: dict) -> tuple:
    """False iff any provided KPI value is NaN/+inf/-inf (or a check errors)."""
    import math

    failures = []
    for name, value in (kpis or {}).items():
        try:
            if hasattr(value, "select_dtypes"):  # pandas DataFrame
                numeric = value.select_dtypes(include="number")
                for col in numeric.columns:
                    for v in numeric[col].tolist():
                        if v is None or not math.isfinite(float(v)):
                            failures.append(f"kpi:{name}.{col} non-finite ({v!r})")
                            return False, failures
            elif isinstance(value, dict):
                stack = [value]
                while stack:
                    node = stack.pop()
                    if isinstance(node, dict):
                        stack.extend(node.values())
                    elif isinstance(node, (list, tuple)):
                        stack.extend(node)
                    elif isinstance(node, (int, float)) and not isinstance(node, bool):
                        if not math.isfinite(float(node)):
                            failures.append(f"kpi:{name} non-finite ({node!r})")
                            return False, failures
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if not math.isfinite(float(value)):
                    failures.append(f"kpi:{name} non-finite ({value!r})")
                    return False, failures
        except Exception as exc:  # noqa: BLE001 - a broken check is BAD, not GOOD
            failures.append(f"kpi:{name} check error: {type(exc).__name__}: {exc}")
            return False, failures
    return True, failures


def evaluate_quality(datasets=None, kpis=None, quarantine=None) -> QualityDecision:
    """Evaluate a snapshot. NEVER raises: an exception yields UNKNOWN.

    Args:
        datasets: name -> DataFrame (the validated business layer).
        kpis: name -> KPI frame/dict from the KPI engine (optional).
        quarantine: optional {"passed": int, "rejected": int} DLQ summary.
    """
    checks: list = []
    failures: list = []
    source: dict = {}
    try:
        datasets = dict(datasets) if datasets else {}
        kpis = dict(kpis) if kpis else {}

        missing = [d for d in REQUIRED_DATASETS if d not in datasets]
        checks.append(
            {
                "name": "datasets_present",
                "ok": not missing,
                "detail": f"missing={missing}" if missing else "all required present",
            }
        )
        if missing:
            failures.append(f"missing required dataset(s): {', '.join(missing)}")

        empty = []
        for name in REQUIRED_DATASETS:
            df = datasets.get(name)
            if df is None:
                continue
            is_empty = bool(getattr(df, "empty", True)) if hasattr(df, "empty") else not df
            source[f"dataset:{name}"] = (
                int(getattr(df, "shape", [0])[0]) if hasattr(df, "shape") else 0
            )
            if is_empty:
                empty.append(name)
        checks.append(
            {
                "name": "datasets_non_empty",
                "ok": not empty,
                "detail": f"empty={empty}" if empty else "all non-empty",
            }
        )
        if empty:
            failures.append(f"empty validated dataset(s): {', '.join(empty)}")

        kpi_missing = [k for k in REQUIRED_KPIS if k not in kpis]
        if kpis:
            checks.append(
                {
                    "name": "kpi_inputs_present",
                    "ok": not kpi_missing,
                    "detail": f"missing={kpi_missing}" if kpi_missing else "required KPIs present",
                }
            )
            if kpi_missing:
                failures.append(f"missing required KPI input(s): {', '.join(kpi_missing)}")

        if kpis:
            finite_ok, finite_failures = _finite_check(kpis)
            checks.append(
                {
                    "name": "kpi_values_finite",
                    "ok": finite_ok,
                    "detail": finite_failures[0] if finite_failures else "no NaN/inf",
                }
            )
            if not finite_ok:
                failures.extend(finite_failures)

        if isinstance(quarantine, dict) and "rejected" in quarantine:
            passed = int(quarantine.get("passed", 0) or 0)
            rejected = int(quarantine.get("rejected", 0) or 0)
            total = passed + rejected
            rate = (rejected / total) if total else 0.0
            ok = rate <= QUARANTINE_RATE_MAX
            checks.append(
                {
                    "name": "quarantine_rate",
                    "ok": ok,
                    "detail": f"rate={rate:.3f} (max={QUARANTINE_RATE_MAX})",
                }
            )
            if not ok:
                failures.append(f"quarantine rate {rate:.3f} exceeds {QUARANTINE_RATE_MAX}")
        else:
            checks.append(
                {
                    "name": "quarantine_rate",
                    "ok": True,
                    "detail": "not_provided (row-level gate already quarantined)",
                }
            )

        period = {}
        for name in ("production", "machine"):
            df = datasets.get(name)
            if hasattr(df, "columns") and "Date" in df.columns and len(df):
                period[f"{name}_min"] = str(df["Date"].min())
                period[f"{name}_max"] = str(df["Date"].max())

        status = GOOD if not failures else BAD
        reason = "all checks passed" if not failures else "; ".join(failures)[:500]
        return QualityDecision(
            status=status,
            checks=checks,
            failures=failures,
            source=source,
            period=period,
            reason=reason,
        )
    except Exception as exc:  # noqa: BLE001 - gate failure must fail closed
        return QualityDecision(
            status=UNKNOWN,
            checks=checks,
            failures=failures,
            source=source,
            reason=f"quality evaluation error: {type(exc).__name__}: {exc}"[:500],
        )
