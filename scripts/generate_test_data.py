"""Canonical entry point for the reproducible test fixture.

The generator itself lives in `generate_sample_data.py` and predates this
wrapper. Rather than move ~330 lines and churn the CI workflow that already
calls it, this module is the documented name referenced by the portfolio
workflow:

    git clone
      -> python -m scripts.generate_test_data    # this module
      -> python -m scripts.verify_fixture        # hashes must match
      -> pytest

Guarantees
----------
* **Fixed seed** - SEED=42 in the generator. The same seed on any machine, on
  any day, produces byte-identical CSVs. Nothing reads the wall clock, the
  process hash seed, or the environment.
* **Documented row count** - every dataset's row count is written into
  `_fixture_manifest.json` and echoed by `--show`.
* **Schema version** - `factory-fixture-v1`, recorded in the manifest and
  asserted by `verify_fixture.py`.
* **Expected SHA/checksum** - per-file SHA-256 plus a hash of the manifest
  itself, so a hand-edited expectation is detected before it is trusted.

Nothing large is committed: the CSVs stay gitignored and are reproduced from
this script in seconds.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.generate_sample_data import (  # noqa: E402
    FIXTURE_SCHEMA_VERSION,
    SEED,
    generate,
)

# Alias kept so callers and docs can use the manifest name without importing a
# private helper from the verifier.
MANIFEST_NAME = "_fixture_manifest.json"


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic test fixture (seeded, checksummed)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="number of days to simulate (default 90; part of the fixture identity)",
    )
    parser.add_argument("--output-dir", default=None, help="defaults to data/raw")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the per-dataset summary (manifest is still written)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="print the manifest JSON after generating",
    )
    args = parser.parse_args(argv)

    out = args.output_dir
    if out is None:
        from app.utils.config import DATA_RAW_DIR

        out = DATA_RAW_DIR

    generate(days=args.days, output_dir=out, quiet=args.quiet)

    manifest_path = os.path.join(out, MANIFEST_NAME)
    if args.show and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            print(json.dumps(json.load(fh), indent=2, sort_keys=True))

    print(
        f"\nFixture ready. schema={FIXTURE_SCHEMA_VERSION} seed={SEED} "
        f"days={args.days}\nNext: python -m scripts.verify_fixture --output-dir {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
