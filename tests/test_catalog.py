"""
Test Catalog registry + Lineage — lớp ④ Cataloging & Search.

Không chỉ test object tồn tại: mỗi hành vi được kiểm bằng kết quả quan sát được.
"""

from __future__ import annotations

import json

import pytest

from app.catalog.registry import ZONE_ORDER, Catalog, CatalogError, seed_default_catalog


@pytest.fixture
def cat() -> Catalog:
    c = Catalog(path="/dev/null")
    c.register(
        name="raw_a", description="raw A", owner="team-data", zone="RAW", source=[], version="1.0.0"
    )
    c.register(
        name="silver_a",
        description="silver A",
        owner="team-data",
        zone="SILVER",
        source=["raw_a"],
        version="1.0.0",
        consumers=["gold_a"],
    )
    c.register(
        name="gold_a",
        description="gold A",
        owner="team-data",
        zone="GOLD",
        source=["silver_a"],
        version="1.0.0",
    )
    c.register(
        name="mart_a",
        description="mart A",
        owner="team-bi",
        zone="MART",
        source=["gold_a"],
        version="1.0.0",
    )
    return c


# ==========================================================================
# Catalog — register / get / list / update
# ==========================================================================
def test_register_then_get_returns_entry(cat):
    e = cat.get("gold_a")
    assert e.zone == "GOLD"
    assert e.owner == "team-data"
    assert "gold_a" in cat
    assert len(cat) == 4


def test_duplicate_registration_raises(cat):
    with pytest.raises(CatalogError, match="đã đăng ký"):
        cat.register(name="gold_a", description="x", owner="o", zone="GOLD", source=[], version="9")


def test_unknown_dataset_raises_with_helpful_message(cat):
    with pytest.raises(CatalogError, match="Đã biết"):
        cat.get("khong_ton_tai")


def test_missing_required_field_raises():
    c = Catalog(path="/dev/null")
    with pytest.raises(CatalogError, match="owner"):
        c.register(name="x", description="d", zone="RAW", source=[], version="1")


def test_invalid_zone_rejected(cat):
    with pytest.raises(CatalogError, match="zone"):
        cat.register(
            name="bad", description="d", owner="o", zone="GOLD_LAKE", source=[], version="1"
        )


def test_list_sorted_by_medallion_zone_order(cat):
    assert [e.zone for e in cat.list()] == ["RAW", "SILVER", "GOLD", "MART"]
    assert [e.name for e in cat.list(zone="GOLD")] == ["gold_a"]


def test_update_changes_metadata_not_created_at(cat):
    before_created = cat.get("gold_a").created_at
    cat.update("gold_a", version="2.0.0", consumers=["mart_a"])
    e = cat.get("gold_a")
    assert e.version == "2.0.0"
    assert e.consumers == ["mart_a"]
    assert e.created_at == before_created
    assert e.updated_at >= before_created


def test_update_unknown_raises(cat):
    with pytest.raises(CatalogError):
        cat.update("khong_ton_tai", version="2")


# ==========================================================================
# Catalog — schema + serialization
# ==========================================================================
def test_schema_persists_through_dict_roundtrip(cat):
    cat.update("raw_a", schema={"Date": "date", "Actual_Qty": "int"})
    d = cat.get("raw_a").to_dict()
    assert d["schema"] == {"Date": "date", "Actual_Qty": "int"}
    rebuilt = Catalog(path="/dev/null")
    rebuilt._entries = {"raw_a": type(cat.get("raw_a")).from_dict(d)}
    assert rebuilt.get("raw_a").schema == d["schema"]


def test_serialization_is_deterministic(cat):
    a = json.loads(cat.serialize())
    b = json.loads(cat.serialize())
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b
    assert a["zone_order"] == list(ZONE_ORDER)


def test_serialize_is_valid_json_with_datasets(cat):
    raw = json.loads(cat.serialize())
    assert raw["catalog_version"] == "1.0"
    assert len(raw["datasets"]) == 4


def test_save_load_roundtrip(tmp_path, cat):
    p = cat.save(str(tmp_path / "catalog.json"))
    fresh = Catalog(path=p)
    assert len(fresh) == 4
    assert fresh.get("mart_a").zone == "MART"


# ==========================================================================
# Catalog — validate
# ==========================================================================
def test_validate_clean_catalog_returns_no_problems(cat):
    assert cat.validate() == []


def test_validate_flags_unregistered_source():
    c = Catalog(path="/dev/null")
    c.register(
        name="silver_x",
        description="d",
        owner="o",
        zone="SILVER",
        source=["khong_co_trong_catalog"],
        version="1",
    )
    problems = c.validate()
    assert any("khong_co_trong_catalog" in p for p in problems)


def test_validate_flags_unregistered_consumer():
    c = Catalog(path="/dev/null")
    c.register(
        name="gold_x",
        description="d",
        owner="o",
        zone="GOLD",
        source=[],
        consumers=["khong_ton_tai"],
        version="1",
    )
    assert any("consumer" in p or "khong_ton_tai" in p for p in c.validate())


def test_seed_default_catalog_is_valid():
    c = seed_default_catalog()
    assert c.validate() == []
    assert {e.zone for e in c.list()} == {"RAW", "SILVER", "GOLD"}
    # KHÔNG khai mart vì seed chạy trước khi mart tồn tại; register_marts_in_catalog
    # là nơi duy nhất thêm zone MART.
    assert not any(e.zone == "MART" for e in c.list())


def test_seed_uses_real_gold_dataset_names():
    """Catalog không được tự bịa tên gold khác với module gold."""
    from app.etl.gold import GOLD_DATASETS

    c = seed_default_catalog()
    gold_names = {e.name for e in c.list(zone="GOLD")}
    assert gold_names == set(GOLD_DATASETS)
