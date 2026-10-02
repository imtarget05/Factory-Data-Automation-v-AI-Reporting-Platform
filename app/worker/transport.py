"""The worker's transport seam.

The worker must be the SAME business path whether the broker is Azure Service
Bus or something local, or the local proof proves nothing about production. So
the transport is reduced to two operations and the semantics of each is stated
here rather than left to a specific SDK:

    receive()   -> Delivery | None
    settle(d, action)

The critical asymmetry, and the reason this is an interface rather than a helper:
`complete` is IRREVERSIBLE. Once a broker is told a message is done it will not
deliver it again, so calling it before durable success loses work permanently
and no retry logic anywhere can recover it. `abandon` is the safe direction --
it returns the message for redelivery -- and is what every non-ACK outcome uses.

No Azure client is constructed here. This wave proves the worker contract
locally; the Azure adapter arrives with live validation and must implement this
same interface, not a parallel path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class SettleAction(StrEnum):
    """What to tell the broker after processing.

    NOT `ack` / `nack` / `retry` on purpose. Those names belong to one broker's
    vocabulary, and this repository has two transports in scope. What matters is
    the irreversible direction, so that is what the name says.
    """

    COMPLETE = "COMPLETE"
    """Irreversible. Only after durable success."""

    ABANDON = "ABANDON"
    """Return to the broker for redelivery. Safe at any point."""


@dataclass(frozen=True)
class Delivery:
    """One received message.

    `body` is the raw payload, deliberately NOT parsed. Parsing belongs to the
    worker so that a malformed message produces a DLQ record with a reason
    rather than an exception thrown from inside the transport.
    """

    message_id: str
    body: Any
    delivery_count: int = 1
    enqueued_at: str | None = None


class Transport(Protocol):
    """The minimum a broker must provide for the worker to run."""

    def receive(self) -> Delivery | None:
        """Return the next message, or None when there is nothing to do."""

    def settle(self, delivery: Delivery, action: SettleAction) -> None:
        """Report the outcome. COMPLETE must never precede durable success."""

    def close(self) -> None:
        """Release the connection so the process can exit cleanly."""


class InMemoryTransport:
    """A local transport for tests and for `python -m app.worker --once`.

    Deliberately tiny and deliberately honest about what it proves: it proves
    the worker's ACK/RETRY/DEAD-LETTER decisions and the durable-state
    interactions around them. It proves nothing about Service Bus itself, which
    is why the status is recorded as IMPLEMENTED_TESTED_LOCAL rather than
    verified against Azure.

    The redelivery behaviour is modelled, not simulated optimistically: a message
    that is ABANDONed goes back with its delivery_count incremented, which is
    what Service Bus does and what the retry-bound tests depend on.
    """

    def __init__(self, bodies: list[Any] | None = None, *, max_deliveries: int = 5) -> None:
        self._queue: list[Delivery] = []
        self._dead: list[tuple[Delivery, str]] = []
        self._settled: list[tuple[str, SettleAction]] = []
        self._max_deliveries = max_deliveries
        for body in bodies or []:
            self.publish(body)

    def publish(self, body: Any, message_id: str = "local") -> None:
        self._queue.append(Delivery(message_id=message_id, body=body))

    def receive(self) -> Delivery | None:
        return self._queue.pop(0) if self._queue else None

    def settle(self, delivery: Delivery, action: SettleAction) -> None:
        self._settled.append((delivery.message_id, action))
        if action is SettleAction.COMPLETE:
            return
        # ABANDON: requeue for redelivery, unless the broker-side retry cap has
        # been hit -- which is how a poison message ends up in the DLQ instead of
        # cycling forever.
        if delivery.delivery_count >= self._max_deliveries:
            self._dead.append((delivery, "delivery count exhausted"))
            return
        self._queue.append(
            Delivery(
                message_id=delivery.message_id,
                body=delivery.body,
                delivery_count=delivery.delivery_count + 1,
            )
        )

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    # ── assertions the tests use instead of reaching into private state ──────

    @property
    def completed(self) -> list[str]:
        return [mid for mid, action in self._settled if action is SettleAction.COMPLETE]

    @property
    def abandoned(self) -> list[str]:
        return [mid for mid, action in self._settled if action is SettleAction.ABANDON]

    @property
    def dead_letters(self) -> list[tuple[Delivery, str]]:
        return list(self._dead)

    @property
    def pending(self) -> int:
        return len(self._queue)
