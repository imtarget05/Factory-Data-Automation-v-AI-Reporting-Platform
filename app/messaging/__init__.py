"""Message transport contracts for the Factory ETL worker."""

from app.messaging.envelope import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_VERSIONS,
    Envelope,
    EnvelopeError,
    TransientEnvelopeError,
    parse_envelope,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_VERSIONS",
    "Envelope",
    "EnvelopeError",
    "TransientEnvelopeError",
    "parse_envelope",
]
