"""The versioned message envelope the worker accepts.

An envelope is the worker's only legitimate source of identity. Three
identifiers are kept deliberately distinct because collapsing any two of them
breaks a different guarantee:

    message_id   transport identity.   A redelivery has a NEW one.
    source_id    what the data IS.     Same source reprocessed keeps it.
    run_id       which execution.      A NEW one per processing run.

The distinction that matters operationally: a retry of a failed stage stays on
the same `run_id` with a new attempt, while reprocessing already-successful work
gets a NEW `run_id` and the SAME `source_id`. If reprocess reused the run_id,
the semantic key `(run_id, stage)` would already be SUCCEEDED and the work
would be silently skipped -- a replay that appears to succeed while doing
nothing.

Version handling FAILS CLOSED. An unknown future version is rejected rather than
best-effort parsed into the current shape: silently accepting a version whose
fields mean something else is how a producer change corrupts data downstream
without any error surfacing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

#: Only one version exists so far. Bumping this is a deliberate act, and
#: SUPPORTED_VERSIONS is the place that makes old readers stop accepting new
#: messages rather than misreading them.
CURRENT_SCHEMA_VERSION = 1
SUPPORTED_VERSIONS = frozenset({1})

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_IDENTIFIER_CHARS = 128

RUN_ID_RE = re.compile(r"^run-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class EnvelopeError(ValueError):
    """The message is not a usable envelope.

    Carries a `retryable` flag because the two failure modes must be handled
    differently: a malformed envelope will never succeed on redelivery, while a
    dependency hiccup during validation might. Subclasses set it explicitly
    rather than letting the caller guess from the type.
    """

    retryable = False

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class TransientEnvelopeError(EnvelopeError):
    """Validation could not complete because of a dependency, not the input."""

    retryable = True


@dataclass(frozen=True)
class Envelope:
    """A validated message. Construct only through `parse_envelope`."""

    schema_version: int
    message_id: str
    source_id: str
    run_id: str
    stage: str
    occurred_at: datetime
    correlation_id: str
    payload: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        """Safe fields for logs and DLQ records.

        Deliberately excludes `payload`: it is unbounded and may carry telemetry
        or anything else that should not be copied into a log line or a
        dead-letter record. The identity fields are what an operator needs to
        find the message again.
        """
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "source_id": self.source_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
            "payload_bytes": len(json.dumps(self.payload, default=str).encode("utf-8")),
        }


def _require_identifier(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EnvelopeError("ENVELOPE_FIELD_MISSING", f"{field} must be a non-empty string")
    if len(value) > MAX_IDENTIFIER_CHARS:
        raise EnvelopeError(
            "ENVELOPE_FIELD_TOO_LONG",
            f"{field} exceeds {MAX_IDENTIFIER_CHARS} characters",
        )
    return value.strip()


def _parse_occurred_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EnvelopeError("ENVELOPE_TIMESTAMP_INVALID", "occurred_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EnvelopeError(
            "ENVELOPE_TIMESTAMP_INVALID", f"occurred_at is not ISO-8601: {value}"
        ) from exc
    # A naive timestamp is rejected rather than assumed to be UTC. Guessing here
    # would put the message in the wrong lease window on a machine in another
    # timezone, and the symptom would be an unexplained early retry.
    if parsed.tzinfo is None:
        raise EnvelopeError(
            "ENVELOPE_TIMESTAMP_NAIVE", "occurred_at must carry an explicit timezone offset"
        )
    return parsed.astimezone(timezone.utc)


def parse_envelope(raw: Any, *, stage_validator: Any = None) -> Envelope:
    """Validate and parse one message body.

    Every rejection raises EnvelopeError with a stable `code`, because the DLQ
    record and the retry decision both key off that code rather than off the
    message text, which would change with every reword.

    Order matters: the version is checked FIRST so that a v2 message is reported
    as an unsupported version rather than failing piecemeal on fields that may
    not exist yet.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvelopeError("ENVELOPE_ENCODING_INVALID", "body is not valid UTF-8") from exc

    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise EnvelopeError("ENVELOPE_TOO_LARGE", "body exceeds the size limit")
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EnvelopeError("ENVELOPE_JSON_INVALID", f"body is not JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise EnvelopeError("ENVELOPE_NOT_OBJECT", "body must decode to an object")

    version = raw.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise EnvelopeError("ENVELOPE_VERSION_MISSING", "schema_version must be an integer")
    if version not in SUPPORTED_VERSIONS:
        # Fail closed. Accepting an unknown version and reading the fields we
        # happen to recognise is how a producer adds a field that means something
        # different and the pipeline silently processes the wrong thing.
        raise EnvelopeError(
            "ENVELOPE_VERSION_UNSUPPORTED",
            f"schema_version {version} is not supported; this worker reads {sorted(SUPPORTED_VERSIONS)}",
        )

    message_id = _require_identifier(raw, "message_id")
    source_id = _require_identifier(raw, "source_id")
    run_id = _require_identifier(raw, "run_id")
    correlation_id = _require_identifier(raw, "correlation_id")
    stage = _require_identifier(raw, "stage")

    if not RUN_ID_RE.match(run_id):
        # Enforced because run_id IS the semantic key. A malformed one would
        # still be accepted by the database and would silently create a second
        # unit of work for what is actually the same run.
        raise EnvelopeError(
            "ENVELOPE_RUN_ID_MALFORMED", f"run_id is not a UUIDv7 run identifier: {run_id}"
        )

    if stage_validator is not None and stage not in stage_validator:
        raise EnvelopeError("ENVELOPE_STAGE_UNKNOWN", f"unknown stage: {stage}")

    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise EnvelopeError("ENVELOPE_PAYLOAD_INVALID", "payload must be an object")

    if len(json.dumps(payload, default=str).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise EnvelopeError("ENVELOPE_PAYLOAD_TOO_LARGE", "payload exceeds the size limit")

    return Envelope(
        schema_version=version,
        message_id=message_id,
        source_id=source_id,
        run_id=run_id,
        stage=stage,
        occurred_at=_parse_occurred_at(raw.get("occurred_at")),
        correlation_id=correlation_id,
        payload=payload,
    )
