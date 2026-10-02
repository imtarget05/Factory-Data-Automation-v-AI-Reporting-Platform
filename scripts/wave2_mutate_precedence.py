#!/usr/bin/env python3
"""W2-2 negative control: revert 0003's precedence rule to latest-attempt-wins.

WHY THE RESTORE IS A FILE COPY AND NOT `git checkout --`
=========================================================

The first version of this script restored with:

    git checkout -- migrations/versions/0003_semantic_state_split.py

and it destroyed the fix under test. `git checkout --` restores from the index,
and the precedence fix is not committed while the control is running — so the
"restore" silently reverted the very change the mutation was proving matters.
The script's own docstring warned about restoring from the wrong copy, and then
did exactly that.

So the backup is a byte-exact copy taken immediately before mutating, and the
restore verifies the content came back rather than trusting a VCS operation that
may point at a different revision than the one under test.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "migrations" / "versions" / "0003_semantic_state_split.py"

FIXED_ANCHOR = "        WITH ranked AS ("
START = '    op.execute(\n        """\n' + FIXED_ANCHOR
END = 'FROM canonical c\n        """\n    )'

#: Where the pre-mutation copy lives for the lifetime of this process.
BACKUP = Path(tempfile.gettempdir()) / "wave2_0003_pre_mutation.bak"

# The exact statement that shipped before the fix. Latest-wins.
LATEST_WINS = '''    op.execute(
        """
        INSERT INTO stage_executions (
            run_id, stage, status, attempt_count, message_id, correlation_id,
            started_at, completed_at, succeeded_at, output_artifact_ref,
            output_checksum, safe_error_code, safe_error_message,
            created_at, updated_at
        )
        SELECT DISTINCT ON (run_id, stage)
               run_id, stage, status, attempt, message_id, correlation_id,
               started_at, completed_at,
               CASE WHEN status = 'SUCCEEDED'
                    THEN COALESCE(completed_at, updated_at) END,
               output_artifact_ref, output_checksum,
               safe_error_code, safe_error_message, created_at, updated_at
        FROM stage_executions_legacy
        ORDER BY run_id, stage, attempt DESC
        """
    )'''


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if FIXED_ANCHOR not in text:
        print("REFUSING: the fixed statement is not present. Nothing to mutate.", file=sys.stderr)
        return 1
    # Byte-exact backup BEFORE touching anything.
    shutil.copy2(TARGET, BACKUP)
    print(f"backup -> {BACKUP}  sha256={_digest(BACKUP)[:16]}")
    start = text.index(START)
    end = text.index(END) + len(END)
    TARGET.write_text(text[:start] + LATEST_WINS + text[end:], encoding="utf-8")
    print("MUTATION APPLIED: latest-attempt-wins restored in 0003")
    return 0


def restore() -> int:
    if not BACKUP.exists():
        print(
            f"REFUSING: no backup at {BACKUP}. Restoring from git would revert "
            "any fix that is not committed yet — which is exactly the mistake "
            "this script used to make.",
            file=sys.stderr,
        )
        return 1
    shutil.copy2(BACKUP, TARGET)
    ok = FIXED_ANCHOR in TARGET.read_text(encoding="utf-8")
    print(f"RESTORED from {BACKUP}  sha256={_digest(TARGET)[:16]}")
    if not ok:
        print("VERIFY FAILED: the fixed statement is not back", file=sys.stderr)
        return 1
    print("VERIFIED: the precedence fix is present again")
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "apply":
        raise SystemExit(apply())
    if action == "restore":
        raise SystemExit(restore())
    print(__doc__)
    raise SystemExit(2)
