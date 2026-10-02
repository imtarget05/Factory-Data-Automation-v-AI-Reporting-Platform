"""The Factory ETL worker: business processing loop and entrypoint."""

from app.worker.processor import (
    Disposition,
    FailureClass,
    MessageOutcome,
    classify_exception,
    process_one,
)

__all__ = [
    "Disposition",
    "FailureClass",
    "MessageOutcome",
    "classify_exception",
    "process_one",
]
