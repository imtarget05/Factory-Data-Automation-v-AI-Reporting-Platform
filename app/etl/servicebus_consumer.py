"""Service Bus Telemetry Consumer for Factory Data Automation & AI Reporting Platform.

Consumes sensor readings and production events from Azure Service Bus queue
'factory-telemetry-inbox' with:
1. Message deduplication (idempotency window)
2. Contract validation & quarantine routing (DLQ)
3. ETL run manifest recording into PostgreSQL/SQLite
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from app.database.models import ETLRunManifest, QuarantineRecord, SessionLocal

logger = logging.getLogger(__name__)


class TelemetryConsumer:
    """Processes telemetry payloads from Azure Service Bus inbox."""

    def __init__(
        self, connection_string: str | None = None, queue_name: str = "factory-telemetry-inbox"
    ):
        self.connection_string = connection_string
        self.queue_name = queue_name
        self.processed_ids: set[str] = set()

    def process_message(
        self, message: dict[str, Any], message_id: str | None = None
    ) -> dict[str, Any]:
        """Process a single telemetry message with deduplication and contract validation."""
        msg_id = message_id or message.get("id") or message.get("message_id")
        if not msg_id:
            msg_str = json.dumps(message, sort_keys=True)
            msg_id = hashlib.sha256(msg_str.encode("utf-8")).hexdigest()[:16]

        # 1. Deduplication check
        if msg_id in self.processed_ids:
            return {
                "status": "duplicate_skipped",
                "message_id": msg_id,
                "reason": "Message already processed in current ingestion window",
            }

        # 2. Quality validation
        required_fields = ["Machine_ID", "Date", "Line"]
        missing = [f for f in required_fields if f not in message]

        if missing:
            # Route to quarantine
            self._record_quarantine(
                msg_id=msg_id,
                source="servicebus:factory-telemetry-inbox",
                reason=f"Missing mandatory fields: {', '.join(missing)}",
                raw_payload=json.dumps(message),
            )
            self.processed_ids.add(msg_id)
            return {
                "status": "quarantined",
                "message_id": msg_id,
                "reason": f"Contract violation: missing {missing}",
            }

        # Value ranges check
        speed = message.get("Speed_RPM")
        if speed is not None and (not isinstance(speed, (int, float)) or speed < 0):
            self._record_quarantine(
                msg_id=msg_id,
                source="servicebus:factory-telemetry-inbox",
                reason=f"Invalid Speed_RPM: {speed}",
                raw_payload=json.dumps(message),
            )
            self.processed_ids.add(msg_id)
            return {
                "status": "quarantined",
                "message_id": msg_id,
                "reason": "Negative or non-numeric speed",
            }

        self.processed_ids.add(msg_id)
        return {
            "status": "accepted",
            "message_id": msg_id,
            "machine_id": message.get("Machine_ID"),
            "processed_at": datetime.utcnow().isoformat(),
        }

    def process_batch(
        self, messages: list[dict[str, Any]], run_id: str | None = None
    ) -> dict[str, Any]:
        """Process a batch of telemetry messages and log ETL run manifest."""
        run_key = run_id or f"run-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        started_at = datetime.utcnow()
        ingested = 0
        quarantined = 0
        duplicates = 0

        for msg in messages:
            res = self.process_message(msg)
            if res["status"] == "accepted":
                ingested += 1
            elif res["status"] == "quarantined":
                quarantined += 1
            elif res["status"] == "duplicate_skipped":
                duplicates += 1

        completed_at = datetime.utcnow()
        checksum = hashlib.sha256(
            json.dumps(messages, default=str, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # Record manifest
        self._record_manifest(
            run_id=run_key,
            started_at=started_at,
            completed_at=completed_at,
            status="SUCCESS",
            rows_ingested=ingested,
            rows_quarantined=quarantined,
            checksum_sha256=checksum,
        )

        return {
            "run_id": run_key,
            "status": "SUCCESS",
            "rows_ingested": ingested,
            "rows_quarantined": quarantined,
            "duplicates_skipped": duplicates,
            "checksum": checksum,
        }

    def _record_quarantine(self, msg_id: str, source: str, reason: str, raw_payload: str) -> None:
        try:
            db = SessionLocal()
            rec = QuarantineRecord(
                run_id=msg_id,
                source_file=source,
                rejection_reason=reason,
                raw_payload=raw_payload,
                quarantined_at=datetime.utcnow(),
            )
            db.add(rec)
            db.commit()
            db.close()
        except Exception as e:
            logger.warning("Could not persist quarantine record to DB: %s", e)

    def _record_manifest(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        rows_ingested: int,
        rows_quarantined: int,
        checksum_sha256: str,
    ) -> None:
        try:
            db = SessionLocal()
            manifest = ETLRunManifest(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                rows_ingested=rows_ingested,
                rows_quarantined=rows_quarantined,
                checksum_sha256=checksum_sha256,
            )
            db.add(manifest)
            db.commit()
            db.close()
        except Exception as e:
            logger.warning("Could not persist run manifest to DB: %s", e)
