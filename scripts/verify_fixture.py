"""Verify the generated fixture against its committed manifest.

Why a separate tool
-------------------
`generate_sample_data.py` writes both the CSVs and the manifest, so running it
alone can never fail: it would just agree with itself. The question that
matters to a reviewer is different -- *does a fresh generation still reproduce
the committed expectation?* -- and that needs a check that reads the manifest
without rewriting it.

This is the `verify fixture metadata` step of the canonical workflow:

    git clone
      -> python -m scripts.generate_test_data     (seeded, deterministic)
      -> python -m scripts.verify_fixture         (hashes must match)
      -> pytest

Usage
-----
    python -m scripts.verify_fixture                    # verify data/raw/
    python -m scripts.verify_fixture --output-dir DIR
    python -m scripts.verify_fixture --blessed docs/expected/factory-fixture.json

`--blessed` compares against a manifest stored outside the gitignored data dir,
which is the stronger check: it fails if someone regenerates and re-blesses
locally without the change being reviewed.

Exit codes: 0 = match, 1 = mismatch or missing fixture.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.generate_sample_data import _sha256  # noqa: E402

MANIFEST_NAME = "_fixture_manifest.json"


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _manifest_self_hash(manifest: dict) -> str:
    """Recompute the manifest's own hash over the payload without the hash."""
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(payload.encode()).hexdigest()


def verify(manifest_dir: str, blessed_path: str | None = None) -> int:
    local_path = os.path.join(manifest_dir, MANIFEST_NAME)
    if not os.path.exists(local_path):
        print(f"FAIL: no manifest at {local_path}")
        print("      run: python -m scripts.generate_test_data")
        return 1

    local = _load(local_path)
    reference = _load(blessed_path) if blessed_path else local
    origin = "blessed reference" if blessed_path else "local manifest"

    failures: list[str] = []

    # 1. The manifest must not have been edited by hand. Checking this first
    #    means a tampered expectation cannot make the file-by-file comparison
    #    below pass by agreeing with itself.
    recomputed = _manifest_self_hash(local)
    if local.get("manifest_sha256") != recomputed:
        failures.append(
            f"{local_path}: manifest_sha256 does not match its own contents "
            f"(recorded {local.get('manifest_sha256')}, actual {recomputed})"
        )

    # 2. Generation parameters must match, or the row-count comparison below is
    #    meaningless -- different --days legitimately produces different files.
    for field in ("schema_version", "seed", "days"):
        if local.get(field) != reference.get(field):
            failures.append(
                f"{field}: local {local.get(field)!r} != {origin} {reference.get(field)!r}"
            )

    # 3. Every file the reference expects must exist locally with the same bytes.
    ref_datasets = reference.get("datasets", {})
    local_datasets = local.get("datasets", {})
    for name, expected in sorted(ref_datasets.items()):
        actual = local_datasets.get(name)
        if actual is None:
            failures.append(f"{name}: missing from freshly generated fixture")
            continue
        if actual.get("rows") != expected.get("rows"):
            failures.append(
                f"{name}: row count {actual.get('rows')} != expected {expected.get('rows')}"
            )
        if actual.get("sha256") != expected.get("sha256"):
            failures.append(
                f"{name}: sha256 {actual.get('sha256')} != expected {expected.get('sha256')}"
            )
            continue
        path = os.path.join(manifest_dir, name)
        if not os.path.exists(path):
            failures.append(f"{name}: manifest lists it but the file is absent")
            continue
        on_disk = _sha256(path)
        if on_disk != expected.get("sha256"):
            failures.append(
                f"{name}: file on disk hashes {on_disk}, manifest claims {expected.get('sha256')}"
            )

    extra = set(local_datasets) - set(ref_datasets)
    for name in sorted(extra):
        failures.append(f"{name}: present in fixture but not in the {origin}")

    if failures:
        print(f"FIXTURE VERIFY: FAIL ({len(failures)} problem(s))")
        for f in failures:
            print(f"  - {f}")
        print()
        print("If this change is intended, re-bless deliberately and review the diff:")
        print("  python -m scripts.generate_test_data")
        print("  python -m scripts.write_blessed_fixture")
        return 1

    print(
        f"FIXTURE VERIFY: PASS  schema={local['schema_version']} "
        f"seed={local['seed']} days={local['days']} "
        f"datasets={len(ref_datasets)} total_rows={local.get('total_rows')}"
    )
    return 0


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the generated fixture matches its manifest."
    )
    parser.add_argument("--output-dir", default=None, help="defaults to data/raw")
    parser.add_argument(
        "--blessed",
        default=None,
        help="manifest to compare against, e.g. docs/expected/factory-fixture.json",
    )
    args = parser.parse_args(argv)

    out = args.output_dir
    if out is None:
        from app.utils.config import DATA_RAW_DIR

        out = DATA_RAW_DIR
    return verify(out, args.blessed)


if __name__ == "__main__":
    raise SystemExit(main())
