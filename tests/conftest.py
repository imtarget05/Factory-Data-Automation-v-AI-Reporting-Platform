"""Shared pytest fixtures.

`data/raw/` is gitignored, so a fresh clone has no input data. Without a seed
the two discovery tests in `tests/test_etl.py` can only fail. This fixture
makes `pytest` self-sufficient on a bare clone: it runs the committed
deterministic generator once per session, and only when the data is actually
missing, so it never slows down or changes the behaviour of an already-seeded
run.
"""
import glob
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.utils.config import DATA_RAW_DIR  # noqa: E402


def _has_data() -> bool:
    return bool(glob.glob(os.path.join(DATA_RAW_DIR, "*.csv")))


@pytest.fixture(scope="session", autouse=True)
def sample_data():
    """Generate data/raw/*.csv if the repository has none (bare clone)."""
    if not _has_data():
        from scripts.generate_sample_data import generate

        print("\n[conftest] data/raw is empty - generating sample data (seed 42)")
        generate(quiet=True)
        print(f"[conftest] generated: {len(glob.glob(os.path.join(DATA_RAW_DIR, '*.csv')))} CSV files")
    yield DATA_RAW_DIR
