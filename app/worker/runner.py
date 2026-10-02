"""The worker's run loop: receive, process, settle, repeat.

This is the ONLY place a transport is settled. Centralising it is what makes
"ACK only after durable success" auditable: there is exactly one call to
`COMPLETE`, it is guarded by `outcome.acked`, and `process_one` is the only
producer of that flag. A future contributor adding a second settle site is then
a visible diff rather than a silent second policy.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session, sessionmaker

from app.worker.processor import Disposition, MessageOutcome, process_one
from app.worker.transport import Delivery, SettleAction, Transport

logger = logging.getLogger(__name__)

#: Maps the worker's decision onto the irreversible-direction transport verb.
#: Only ACK and ACK_DUPLICATE mean COMPLETE. Everything else returns the
#: message, because the durable state does not yet say the work is done.
_SETTLE_BY_DISPOSITION: dict[Disposition, SettleAction] = {
    Disposition.ACK: SettleAction.COMPLETE,
    Disposition.ACK_DUPLICATE: SettleAction.COMPLETE,
    Disposition.DEFER: SettleAction.ABANDON,
    Disposition.RETRY: SettleAction.ABANDON,
    Disposition.DEAD_LETTER: SettleAction.ABANDON,
}


@dataclass
class LoopStats:
    received: int = 0
    completed: int = 0
    duplicates: int = 0
    deferred: int = 0
    retried: int = 0
    dead_lettered: int = 0

    def record(self, outcome: MessageOutcome) -> None:
        # if/elif rather than `match`: ruff's target-version is py39, so a
        # match statement reads as a syntax error to the configured linter even
        # though the runtime is 3.12. Staying with the older form costs five
        # lines and keeps the declared floor honest.
        disposition = outcome.disposition
        if disposition is Disposition.ACK:
            self.completed += 1
        elif disposition is Disposition.ACK_DUPLICATE:
            self.duplicates += 1
        elif disposition is Disposition.DEFER:
            self.deferred += 1
        elif disposition is Disposition.RETRY:
            self.retried += 1
        elif disposition is Disposition.DEAD_LETTER:
            self.dead_lettered += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "completed": self.completed,
            "duplicates": self.duplicates,
            "deferred": self.deferred,
            "retried": self.retried,
            "dead_lettered": self.dead_lettered,
        }


def run_once(
    session: Session,
    transport: Transport,
    delivery: Delivery,
    *,
    stage_handler: Callable[[Any], dict[str, Any]],
    owner: str,
    stats: LoopStats | None = None,
) -> MessageOutcome:
    """Process one delivery and settle the transport accordingly.

    Returns the outcome so a caller (or a test) can assert on the decision rather
    than inferring it from transport side effects.
    """
    stats = stats if stats is not None else LoopStats()
    stats.received += 1

    outcome = process_one(
        session,
        delivery.body,
        stage_handler=stage_handler,
        owner=owner,
    )

    action = _SETTLE_BY_DISPOSITION[outcome.disposition]
    # The guard is redundant with the mapping and is kept deliberately: it makes
    # the invariant checkable at the one place where an irreversible action is
    # issued, so a future mapping edit that lets a non-success outcome complete
    # fails loudly here instead of silently acking lost work.
    if action is SettleAction.COMPLETE and not outcome.acked:
        raise RuntimeError(
            f"refusing to settle COMPLETE for {outcome.disposition}: "
            "durable success was not recorded"
        )

    transport.settle(delivery, action)
    stats.record(outcome)
    logger.info("settled", extra=outcome.summary())
    return outcome


def run_loop(
    session_factory: sessionmaker,
    transport: Transport,
    *,
    stage_handler: Callable[[Any], dict[str, Any]],
    owner: str,
    poll_interval: float = 1.0,
    max_messages: int | None = None,
    install_signal_handlers: bool = True,
) -> LoopStats:
    """Receive and process until told to stop.

    Bounded by `max_messages` so the loop is testable and so a container health
    probe can drain rather than hang. Shutdown is cooperative and happens at a
    message boundary: an in-flight `process_one` is never abandoned mid-commit,
    because that is exactly the window that produces a redelivery nobody expects.

    A fresh Session per message. Sharing one across iterations would reuse a
    connection across the long idle periods between deliveries and hold a
    transaction snapshot open for the whole run.
    """
    stats = LoopStats()
    stopping = False

    def _stop(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        logger.info("shutdown requested (signal %s); will stop at the next boundary", signum)

    if install_signal_handlers:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _stop)

    try:
        while not stopping:
            if max_messages is not None and stats.received >= max_messages:
                break
            delivery = transport.receive()
            if delivery is None:
                if max_messages is not None:
                    break
                time.sleep(poll_interval)
                continue

            session: Session = session_factory()
            try:
                run_once(
                    session,
                    transport,
                    delivery,
                    stage_handler=stage_handler,
                    owner=owner,
                    stats=stats,
                )
            except Exception:
                # The session is unusable after an unexpected error, and the
                # delivery has NOT been settled -- so the message returns to the
                # broker and is retried rather than being silently dropped.
                session.rollback()
                logger.exception("unhandled error while processing a delivery; leaving unsettled")
                raise
            finally:
                session.close()
    finally:
        transport.close()
        logger.info("worker stopped", extra=stats.as_dict())

    return stats
