"""`python -m app.worker` -- the runnable ETL worker process.

Runs the SAME `run_loop` the tests drive, so a green worker suite is evidence
about this process rather than about a test-only code path. That distinction is
the whole point: a worker whose entrypoint is a separate implementation is a
worker whose behaviour under SIGTERM has never been exercised.

Deliberate scope of this wave:

  WORKER_TRANSPORT_CONTRACT  IMPLEMENTED_TESTED_LOCAL
  ACK_SEMANTICS              IMPLEMENTED_TESTED
  AZURE_SERVICE_BUS_RUNTIME  NOT_VERIFIED

The local transport is a real implementation of the `Transport` protocol, not a
mock, but it is not Azure Service Bus. Nothing here should be read as evidence
that the broker integration works; that arrives with live validation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.messaging.envelope import Envelope
from app.utils.config import DATABASE_URL
from app.worker.runner import run_loop
from app.worker.transport import InMemoryTransport

logger = logging.getLogger("app.worker")


def default_stage_handler(envelope: Envelope) -> dict[str, object]:
    """Placeholder stage body until the real stage implementations land in W2-5.

    Returns evidence rather than doing nothing, so the durable output columns are
    exercised end to end now. It performs NO external side effect, which is what
    makes the crash tests assert honestly: a real handler would need an artifact
    store, and faking one here would let a duplicate-execution bug hide.
    """
    payload_bytes = len(json.dumps(envelope.payload, default=str).encode("utf-8"))
    return {
        "artifact_ref": f"local://{envelope.run_id}/{envelope.stage}",
        "checksum": f"{payload_bytes:016x}",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.worker", description="Factory ETL worker")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DATABASE_URL),
        help="SQLAlchemy URL for the durable run-state database",
    )
    parser.add_argument(
        "--owner",
        default=os.getenv("FACTORY_WORKER_OWNER"),
        help="stable identity for this worker instance; empty means generate one",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="stop after N messages; omit to run until signalled",
    )
    parser.add_argument(
        "--drain",
        action="store_true",
        help="process everything currently queued, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    owner = args.owner or f"worker-{os.getpid()}"
    # A local transport here only. The Azure adapter implements the same
    # Transport protocol and plugs in at this line.
    transport = InMemoryTransport(max_deliveries=int(os.getenv("FACTORY_MAX_DELIVERIES", "5")))
    engine = create_engine(args.database_url, future=True, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, future=True)

    logger.info(
        "worker starting",
        extra={"owner": owner, "transport": "in-memory", "drain": args.drain},
    )

    max_messages = 1 if args.drain else args.max_messages
    stats = run_loop(
        session_factory,
        transport,
        stage_handler=default_stage_handler,
        owner=owner,
        max_messages=max_messages,
        # Signal handlers are meaningless for a drain and only add noise in tests.
        install_signal_handlers=not args.drain,
    )

    logger.info("worker finished", extra=stats.as_dict())
    print(json.dumps(stats.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
