"""The worker's business loop: one message in, one outcome out.

The single invariant this module exists to protect:

    ACK only after durable success.

Service Bus is at-least-once, so a message can be redelivered at any point. The
only thing that makes redelivery safe is that every externally visible effect is
tied to a durable semantic key `(run_id, stage)` which is committed BEFORE the
message is acknowledged. If those two commits are swapped, the worker can
acknowledge work it never recorded, or record work it never acknowledged, and
the broker's own retry logic cannot tell the difference.

The processing order is therefore fixed and not negotiable:

    parse envelope
      -> claim_stage(run_id, stage)      who executes this?
      -> run the stage                   the side effect
      -> complete_stage()                durable SUCCEEDED  <-- commit point
      -> commit the transaction
      -> ACK                             only now

Anything that fails before the commit leaves the stage claimable, so a
redelivery retries. Anything that fails after the commit is a duplicate that
`claim_stage` resolves as ALREADY_SUCCEEDED without executing again. There is
no third case, and no window where both happen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.etl.stage_claim import ClaimOutcome, claim_stage, complete_stage
from app.etl.stage_execution import MAX_ATTEMPTS_DEFAULT, Stage
from app.messaging.envelope import Envelope, EnvelopeError, parse_envelope

logger = logging.getLogger(__name__)

STAGE_VALUES = frozenset(s.value for s in Stage)


class Disposition(StrEnum):
    """What the worker decided to do with a message.

    Named after the transport action, not after the internal state, because the
    transport action is what the caller must not get wrong.
    """

    ACK = "ACK"
    """Durable success committed. Safe to acknowledge."""

    ACK_DUPLICATE = "ACK_DUPLICATE"
    """Already SUCCEEDED. No side effect. Safe to acknowledge."""

    DEFER = "DEFER"
    """Another worker holds a live claim. Release for redelivery, no ACK."""

    RETRY = "RETRY"
    """Transient failure. Release for redelivery, no ACK."""

    DEAD_LETTER = "DEAD_LETTER"
    """Permanent failure or spent retry budget. Route to the DLQ, no ACK."""


class FailureClass(StrEnum):
    """Why something failed, in terms the retry policy can act on.

    A blanket `except Exception -> retry` is what turns a poison message into
    an infinite loop and a transient blip into a lost run. The class is part of
    the decision, not a label attached afterwards.
    """

    TRANSIENT = "TRANSIENT"
    """A dependency is unavailable. Retry with backoff."""

    BUSINESS_INVALID = "BUSINESS_INVALID"
    """The input cannot ever succeed. Quarantine or dead-letter immediately."""

    PERMANENT = "PERMANENT"
    """Infrastructure refused in a way that will not change on retry."""


@dataclass(frozen=True)
class MessageOutcome:
    """The full result for one message, including what was NOT done.

    `side_effects` is carried so the tests can assert the single most important
    property directly: that a redelivery leaves the count at one.
    """

    disposition: Disposition
    message_id: str
    run_id: str
    stage: str
    claim_outcome: ClaimOutcome | None = None
    attempt: int | None = None
    side_effects: int = 0
    error_class: FailureClass | None = None
    error_code: str | None = None
    detail: str | None = None
    acked: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """Safe, loggable form. No payload: it is unbounded and possibly sensitive."""
        return {
            "disposition": self.disposition.value,
            "message_id": self.message_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "claim_outcome": self.claim_outcome.value if self.claim_outcome else None,
            "attempt": self.attempt,
            "side_effects": self.side_effects,
            "error_class": self.error_class.value if self.error_class else None,
            "error_code": self.error_code,
            "acked": self.acked,
        }


#: Transport errors worth retrying. Matched narrowly on purpose: a broad
#: isinstance/except sweep would also catch a bad envelope and a constraint
#: violation, both of which are permanent and must reach the DLQ instead of
#: burning the retry budget on a message that will never work.
TRANSIENT_DB_ERRORS = ("OperationalError", "InterfaceError", "DBAPIError", "TimeoutError")


def classify_exception(exc: BaseException) -> FailureClass:
    """Decide whether `exc` deserves another attempt.

    Connection-shaped failures are transient because the next attempt usually
    succeeds. Everything else is treated as permanent, which is the safe
    default: a wrongly-abandoned message is visible in the DLQ, while a wrongly
    retried poison message silently consumes the budget and delays everything
    behind it.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return FailureClass.TRANSIENT
    if type(exc).__name__ in TRANSIENT_DB_ERRORS:
        return FailureClass.TRANSIENT
    return FailureClass.PERMANENT


def process_one(
    session: Session,
    raw_body: Any,
    *,
    stage_handler: Callable[[Envelope], dict[str, Any]],
    owner: str,
    lease_seconds: int = 60,
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
) -> MessageOutcome:
    """Process one message and decide what the transport should do with it.

    `stage_handler` performs the actual work and returns a small dict stored as
    the stage's output evidence. It must be IDEMPOTENT with respect to
    `(run_id, stage)`: it can be called again after a crash between the side
    effect and the commit, and the architecture does not pretend otherwise.
    There is no distributed transaction spanning Blob, PostgreSQL and the
    broker, so the claim is what makes a repeat safe -- not the handler.
    """
    # ── 1. Envelope. A bad envelope never reaches business logic, and never
    #       reaches the claim table either: there is no run_id to key on.
    try:
        envelope = parse_envelope(raw_body, stage_validator=STAGE_VALUES)
    except EnvelopeError as exc:
        cls = FailureClass.TRANSIENT if exc.retryable else FailureClass.BUSINESS_INVALID
        logger.warning(
            "envelope rejected", extra={"code": exc.code, "error": str(exc), "class": cls.value}
        )
        return MessageOutcome(
            disposition=Disposition.DEAD_LETTER,
            message_id="<unparsed>",
            run_id="",
            stage="",
            error_class=cls,
            error_code=exc.code,
            detail=str(exc),
            acked=False,
        )

    stage = Stage(envelope.stage)

    # ── 2. Claim. The database decides ownership; this code only reacts to the
    #       verdict. Anything other than an *_ACQUIRED_* outcome means this
    #       worker must NOT execute.
    claim = claim_stage(
        session,
        run_id=envelope.run_id,
        stage=stage,
        owner=owner,
        message_id=envelope.message_id,
        correlation_id=envelope.correlation_id,
        lease_seconds=lease_seconds,
    )
    session.commit()

    if claim.outcome is ClaimOutcome.ALREADY_SUCCEEDED:
        # The redelivery case C4 exists for: durable success was committed before
        # the crash, so there is nothing to redo. ACK without executing.
        # `side_effects` stays 0 for THIS delivery, which is exactly what the
        # crash tests assert.
        logger.info(
            "duplicate of completed work; acknowledging without executing",
            extra=envelope.summary(),
        )
        return MessageOutcome(
            disposition=Disposition.ACK_DUPLICATE,
            message_id=envelope.message_id,
            run_id=envelope.run_id,
            stage=envelope.stage,
            claim_outcome=claim.outcome,
            attempt=None,
            side_effects=0,
            acked=True,
        )

    if claim.outcome is ClaimOutcome.ALREADY_RUNNING:
        # Another worker holds a live lease. Do NOT execute and do NOT ack: an
        # ack here would discard the message while the other worker may still
        # fail, leaving the stage RUNNING with no future delivery.
        logger.info("stage claimed by another worker; deferring", extra=envelope.summary())
        return MessageOutcome(
            disposition=Disposition.DEFER,
            message_id=envelope.message_id,
            run_id=envelope.run_id,
            stage=envelope.stage,
            claim_outcome=claim.outcome,
            acked=False,
        )

    if claim.outcome in (ClaimOutcome.TERMINAL_FAILED, ClaimOutcome.DEAD_LETTERED):
        # Already permanently unsuccessful. Re-executing would retry work that
        # was explicitly given up on; replay is a separate, governed operation
        # that issues a NEW run_id.
        logger.info("stage already terminal; dead-lettering", extra=envelope.summary())
        return MessageOutcome(
            disposition=Disposition.DEAD_LETTER,
            message_id=envelope.message_id,
            run_id=envelope.run_id,
            stage=envelope.stage,
            claim_outcome=claim.outcome,
            error_class=FailureClass.PERMANENT,
            error_code=f"STAGE_{claim.outcome.value}",
            acked=False,
        )

    # ── 3. Execute. From here this worker owns the work.
    try:
        output = stage_handler(envelope)
    except Exception as exc:  # noqa: BLE001 - classification happens below
        cls = classify_exception(exc)
        spent = (claim.attempt or 0) >= max_attempts
        logger.warning(
            "stage handler failed",
            extra={
                **envelope.summary(),
                "attempt": claim.attempt,
                "class": cls.value,
                "spent": spent,
                "error": str(exc)[:200],
            },
        )
        session.rollback()
        # Deliberately NOT writing FAILED/DEAD_LETTERED here. The stage stays
        # claimable via its lease, so a redelivery re-claims it. Marking it
        # terminal on a transient blip would abandon work that would have
        # succeeded, and would also destroy the attempt evidence.
        return MessageOutcome(
            disposition=(
                Disposition.DEAD_LETTER
                if spent or cls is FailureClass.PERMANENT
                else Disposition.RETRY
            ),
            message_id=envelope.message_id,
            run_id=envelope.run_id,
            stage=envelope.stage,
            claim_outcome=claim.outcome,
            attempt=claim.attempt,
            error_class=cls,
            error_code=type(exc).__name__,
            detail=str(exc)[:200],
            acked=False,
        )

    # ── 4. Durable success. THE COMMIT POINT. Everything above is reversible by
    #       a redelivery; everything below is bookkeeping.
    recorded = complete_stage(
        session,
        run_id=envelope.run_id,
        stage=stage,
        attempt=claim.attempt,
        owner=owner,
        output_artifact_ref=(
            str(output.get("artifact_ref")) if output.get("artifact_ref") else None
        ),
        output_checksum=str(output.get("checksum")) if output.get("checksum") else None,
    )
    if not recorded:
        # The lease was recovered while the handler ran, so this result is not
        # authoritative and must not be published. Refusing here is what stops
        # two workers from both publishing an output for one stage.
        session.rollback()
        logger.warning(
            "claim was fenced during execution; discarding result", extra=envelope.summary()
        )
        return MessageOutcome(
            disposition=Disposition.DEFER,
            message_id=envelope.message_id,
            run_id=envelope.run_id,
            stage=envelope.stage,
            claim_outcome=claim.outcome,
            attempt=claim.attempt,
            error_class=FailureClass.TRANSIENT,
            error_code="CLAIM_FENCED",
            acked=False,
        )

    session.commit()

    # ── 5. Only NOW may the caller acknowledge. See the module docstring: this
    #       ordering IS the invariant, and C4 is the test that proves it.
    logger.info("stage completed", extra={**envelope.summary(), "attempt": claim.attempt})
    return MessageOutcome(
        disposition=Disposition.ACK,
        message_id=envelope.message_id,
        run_id=envelope.run_id,
        stage=envelope.stage,
        claim_outcome=claim.outcome,
        attempt=claim.attempt,
        side_effects=1,
        acked=True,
    )
