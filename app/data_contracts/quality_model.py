"""Quality model: an authoritative STATE plus an orthogonal SEVERITY.

READ THIS BEFORE CHANGING ANYTHING HERE
========================================

Two independent dimensions. Neither is derived from the other, and they are not
interchangeable.

**Quality state** -- the trust decision:

    GOOD      the gate ran and every blocking check passed
    BAD       the gate ran and at least one blocking check failed
    UNKNOWN   the gate could NOT obtain enough evidence to decide

**Severity** -- how bad the measured findings are:

    NONE | WARNING | CRITICAL   (null when the state is UNKNOWN)

THE ONE RULE THAT MATTERS
-------------------------

    trusted_report_allowed = (quality_state == GOOD)

That is it. Severity NEVER grants authorization, and `GOOD + CRITICAL` is an
INVALID combination that is rejected rather than coerced.

WHY UNKNOWN IS NOT CRITICAL
---------------------------

They mean opposite things:

    UNKNOWN  -> "we could not measure"
    CRITICAL -> "we measured, and it is seriously wrong"

Collapsing them would make the evidence lie. A result reading "the data is
CRITICAL" when the truth is "we have no idea" is a fabricated finding, and
fabricated findings are the exact failure this gate exists to prevent.

WHY THIS SHAPE
--------------

The shipped gate was ``GOOD | BAD | UNKNOWN`` with a deny-by-default
``status != GOOD`` rule, guarded by 19 regression tests and 4 mutation controls
that must never pass. A later phase specification asked for
``GOOD | WARNING | CRITICAL``.

Adopting that vocabulary directly would have deleted UNKNOWN, turned
deny-by-default into allow-by-default, and invalidated the four mutation
controls. So the vocabulary was NOT replaced. Severity was added alongside it,
which delivers the WARNING the spec wanted while leaving the authorization
shape and all four controls exactly as they were.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "QualityState",
    "Severity",
    "InvalidQualityCombinationError",
    "QualityRuleResult",
    "QualityResult",
    "is_trusted_report_eligible",
    "validate_combination",
]


class QualityState(StrEnum):
    """The trust decision. Unchanged from the shipped gate."""

    GOOD = "GOOD"
    BAD = "BAD"
    UNKNOWN = "UNKNOWN"


class Severity(StrEnum):
    """How bad the measured findings are. Orthogonal to the state."""

    NONE = "NONE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class InvalidQualityCombinationError(ValueError):
    """Raised for a (state, severity) pair that cannot describe a real run."""


# Only these combinations can describe something that actually happened.
# BAD is absent from GOOD's row, so `GOOD + CRITICAL` is rejected rather than
# silently downgraded: if something is critical then something blocking failed,
# so the state is BAD, and reporting GOOD would hide the finding.
# UNKNOWN allows ONLY null, because an unmeasurable gate has no severity at all.
_ALLOWED: dict[QualityState, set[Severity | None]] = {
    QualityState.GOOD: {Severity.NONE, Severity.WARNING},
    QualityState.BAD: {Severity.WARNING, Severity.CRITICAL},
    QualityState.UNKNOWN: {None},
}


def validate_combination(state: QualityState, severity: Severity | None) -> None:
    """Raise ``InvalidQualityCombinationError`` for a pair that cannot occur."""
    if severity not in _ALLOWED[state]:
        shown = severity.value if severity is not None else "null"
        allowed = sorted(s.value if s else "null" for s in _ALLOWED[state])
        raise InvalidQualityCombinationError(
            f"severity={shown!r} is not a valid severity for state={state.value!r}; "
            f"allowed: {allowed}"
        )


@dataclass(frozen=True)
class QualityRuleResult:
    """One deterministic rule's outcome.

    Every field is computed by code, never by a model. ``evidence_ref`` points at
    where the measurement lives; it never carries the measurement itself, because
    a run's raw data does not belong in a ledger row.
    """

    rule_id: str
    rule_version: str
    passed: bool
    blocking: bool
    severity: Severity
    measured_value: float | int | str | None = None
    threshold: float | int | str | None = None
    message: str = ""
    evidence_ref: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "passed": self.passed,
            "blocking": self.blocking,
            "severity": self.severity.value,
            "measured_value": self.measured_value,
            "threshold": self.threshold,
            "message": self.message,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True)
class QualityResult:
    """The outcome of evaluating one run's snapshot.

    Constructed only through ``build`` or ``unknown``, so an impossible
    combination cannot be created at a call site.
    """

    run_id: str
    state: QualityState
    severity: Severity | None
    policy_version: str
    threshold_version: str
    rule_results: tuple[QualityRuleResult, ...] = ()
    reason: str = ""

    @property
    def blocking_rule_count(self) -> int:
        return sum(1 for r in self.rule_results if not r.passed and r.blocking)

    @property
    def warning_rule_count(self) -> int:
        return sum(1 for r in self.rule_results if r.severity is Severity.WARNING)

    @property
    def critical_rule_count(self) -> int:
        return sum(1 for r in self.rule_results if r.severity is Severity.CRITICAL)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "severity": self.severity.value if self.severity else None,
            "policy_version": self.policy_version,
            "threshold_version": self.threshold_version,
            "blocking_rule_count": self.blocking_rule_count,
            "warning_rule_count": self.warning_rule_count,
            "critical_rule_count": self.critical_rule_count,
            "reason": self.reason,
            "rule_results": [r.to_dict() for r in self.rule_results],
        }

    @classmethod
    def unknown(
        cls, run_id: str, reason: str, policy_version: str, threshold_version: str
    ) -> QualityResult:
        """The result of a gate that could not decide.

        The ONLY way to reach UNKNOWN, and it hard-codes ``severity=None``. There
        is deliberately no parameter for it: a caller cannot accidentally report
        a measurement that never happened.
        """
        return cls(
            run_id=run_id,
            state=QualityState.UNKNOWN,
            severity=None,
            policy_version=policy_version,
            threshold_version=threshold_version,
            reason=reason,
        )

    @classmethod
    def build(
        cls,
        run_id: str,
        rule_results: list[QualityRuleResult],
        policy_version: str,
        threshold_version: str,
        reason: str = "",
    ) -> QualityResult:
        """Derive state and severity from the rule results.

        State is derived from the BLOCKING dimension only; severity is derived
        from the findings. Neither reads the other's name, which is what stops a
        rule whose id happens to contain the word "critical" from silently
        deciding authorization.
        """
        blocking_failures = [r for r in rule_results if r.blocking and not r.passed]

        if blocking_failures:
            state = QualityState.BAD
            # A blocking failure exists, so severity is at least WARNING.
            # CRITICAL is warranted only when a rule explicitly measured one --
            # the mere existence of a blocking failure is not evidence of how bad
            # it is, and overstating it would be its own kind of lie.
            severity = (
                Severity.CRITICAL
                if any(r.severity is Severity.CRITICAL for r in rule_results)
                else Severity.WARNING
            )
        else:
            state = QualityState.GOOD
            # Everything blocking passed. A warning here is a real, accepted
            # degradation -- this is the case WARNING exists for, and the reason
            # the spec asked for it.
            severity = (
                Severity.WARNING
                if any(r.severity is Severity.WARNING for r in rule_results)
                else Severity.NONE
            )

        validate_combination(state, severity)
        return cls(
            run_id=run_id,
            state=state,
            severity=severity,
            policy_version=policy_version,
            threshold_version=threshold_version,
            rule_results=tuple(rule_results),
            reason=reason,
        )


def is_trusted_report_eligible(result: QualityResult) -> bool:
    """THE authorization boundary. One function, called from everywhere.

    ``return result.state == QualityState.GOOD``

    NOT ``!= BAD``, and NOT ``severity != CRITICAL``. Those negative forms are
    materially weaker: a state added to the enum later would be ALLOWED by
    ``!= BAD`` and BLOCKED by ``== GOOD``. For a safety gate, an unrecognised
    state must block.

    Severity is deliberately absent. It is diagnostic, and a diagnostic that can
    grant authorization is not a diagnostic.
    """
    return result.state == QualityState.GOOD
