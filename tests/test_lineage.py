"""
Test Lineage — RAW -> SILVER -> GOLD -> MART.

Bám sát hành vi quan sát được: traversal hai chiều, cycle rejection,
idempotent rerun, serialization deterministic.
"""
from __future__ import annotations

import json

import pytest

from app.catalog.lineage import Lineage, LineageError
from app.catalog.registry import seed_default_catalog
from app.etl.gold import GOLD_DATASETS


@pytest.fixture
def lin() -> Lineage:
    l = Lineage(path="/dev/null")
    l.add_edge("raw_production", "silver_production", "etl", run_id="r1")
    l.add_edge("silver_production", "oee_daily", "kpi_aggregate", run_id="r1")
    l.add_edge("silver_production", "quality_daily", "defect_rollup", run_id="r1")
    l.add_edge("oee_daily", "mart_oee", "materialize", run_id="r2")
    return l


# ==========================================================================
# Edge cơ bản
# ==========================================================================
def test_add_edge_records_required_metadata(lin):
    e = [x for x in lin.edges() if x["target_dataset"] == "oee_daily"][0]
    for field in ("source_dataset", "target_dataset", "transform",
                  "run_id", "timestamp"):
        assert field in e, f"thiếu trường edge bắt buộc: {field}"
    assert e["source_dataset"] == "silver_production"
    assert e["transform"] == "kpi_aggregate"
    assert e["run_id"] == "r1"


def test_self_loop_rejected(lin):
    with pytest.raises(LineageError, match="tự vòng"):
        lin.add_edge("oee_daily", "oee_daily", "noop")


def test_empty_source_or_target_rejected(lin):
    with pytest.raises(LineageError, match="rỗng"):
        lin.add_edge("", "oee_daily", "x")
    with pytest.raises(LineageError, match="rỗng"):
        lin.add_edge("raw_production", "", "x")


# ==========================================================================
# Traversal
# ==========================================================================
def test_downstream_direct(lin):
    assert lin.downstream("raw_production") == ["silver_production"]
    assert lin.downstream("silver_production") == [
        "oee_daily", "quality_daily"]


def test_upstream_direct(lin):
    assert lin.upstream("silver_production") == ["raw_production"]
    assert lin.upstream("mart_oee") == ["oee_daily"]


def test_ancestors_transitive_upstream(lin):
    """mart_oee <- gold_oee <- silver <- raw: BFS phải thấy cả 3."""
    assert lin.ancestors("mart_oee") == [
        "oee_daily", "raw_production", "silver_production"]


def test_descendants_transitive_downstream(lin):
    assert lin.descendants("raw_production") == [
        "mart_oee", "oee_daily", "quality_daily", "silver_production"]


def test_leaf_node_has_no_upstream(lin):
    assert lin.upstream("raw_production") == []
    assert lin.descendants("mart_oee") == []


# ==========================================================================
# Cycle detection
# ==========================================================================
def test_backward_edge_creates_cycle_and_is_rejected(lin):
    """gold -> raw sẽ tạo cycle vì đã có raw -> ... -> gold."""
    with pytest.raises(LineageError, match="cycle"):
        lin.add_edge("oee_daily", "raw_production", "reverse")
    assert len(lin) == 4, "edge bị từ chối thì graph không đổi"


def test_multi_hop_cycle_rejected(lin):
    with pytest.raises(LineageError, match="cycle"):
        lin.add_edge("mart_oee", "silver_production", "long_way_back")


def test_diamond_is_not_a_cycle(lin):
    """Hai nhánh hội tụ không phải cycle — phải chấp nhận."""
    lin.add_edge("silver_production", "machine_health", "health", run_id="r1")
    lin.add_edge("machine_health", "mart_oee", "enrich", run_id="r3")
    assert not lin.has_cycle()


def test_has_cycle_false_on_clean_dag(lin):
    assert lin.has_cycle() is False


# ==========================================================================
# Idempotency
# ==========================================================================
def test_duplicate_edge_is_idempotent(lin):
    before = len(lin)
    again = lin.add_edge("raw_production", "silver_production", "etl", run_id="r1")
    assert len(lin) == before, "edge trùng không được nhân bản"
    assert again["transform"] == "etl"


def test_same_pair_different_transform_is_new_edge(lin):
    before = len(lin)
    lin.add_edge("raw_production", "silver_production", "etl_v2", run_id="r9")
    assert len(lin) == before + 1


def test_build_from_catalog_is_idempotent():
    cat = seed_default_catalog()
    a = Lineage(path="/dev/null"); a.build_from_catalog(cat)
    n = len(a)
    b = Lineage(path="/dev/null"); b.build_from_catalog(cat)
    assert len(b) == n, "build lại phải cho cùng số edge"


def test_build_from_catalog_matches_raw_silver_gold():
    cat = seed_default_catalog()
    l = Lineage(path="/dev/null"); l.build_from_catalog(cat)
    assert l.downstream("raw_production") == ["silver_production"]
    assert sorted(l.downstream("silver_production")) == sorted(GOLD_DATASETS)
    assert not l.has_cycle()


def test_catalog_gold_names_match_gold_module_exactly():
    """
    Bắt lỗi tên lệch: catalog gọi 'oee_daily' trong khi gold export
    'oee_daily' thì mart không nối được vào chuỗi lineage.
    """
    from app.database.marts import MART_SOURCE

    cat = seed_default_catalog()
    assert set(GOLD_DATASETS) <= set(cat), "catalog thiếu gold dataset thật"
    for mart, gold_name in MART_SOURCE.items():
        assert cat.has(gold_name), (
            f"{mart} lấy từ '{gold_name}' nhưng catalog không có dataset đó")


def test_full_chain_raw_to_mart_is_connected():
    """Chuỗi phải liền mạch: mart phải truy ngược được về raw."""
    from app.database.marts import register_marts_in_catalog

    cat = seed_default_catalog()
    l = Lineage(path="/dev/null")
    l.build_from_catalog(cat)
    register_marts_in_catalog(cat, l)
    assert l.upstream("mart_oee") == ["oee_daily"]
    assert "raw_production" in l.ancestors("mart_oee")
    assert "mart_oee" in l.descendants("raw_production")


# ==========================================================================
# Serialization
# ==========================================================================
def test_serialization_is_deterministic(lin):
    a = json.loads(lin.serialize())
    b = json.loads(lin.serialize())
    a.pop("generated_at"); b.pop("generated_at")
    assert a == b


def test_edges_sorted_deterministically(lin):
    edges = lin.edges()
    keys = [(e["source_dataset"], e["target_dataset"], e["transform"]) for e in edges]
    assert keys == sorted(keys)


def test_save_load_roundtrip_preserves_graph(tmp_path, lin):
    p = lin.save(str(tmp_path / "lineage.json"))
    fresh = Lineage(path=p)
    assert len(fresh) == len(lin)
    assert fresh.downstream("silver_production") == lin.downstream("silver_production")
    assert fresh.downstream("raw_production") == lin.downstream("raw_production")


def test_graph_method_returns_adjacency(lin):
    g = lin.graph()
    assert g["silver_production"] == ["oee_daily", "quality_daily"]
    assert list(g) == sorted(g)


def test_length_counts_edges_not_nodes(lin):
    assert len(lin) == 4
    nodes = {e["source_dataset"] for e in lin.edges()} | {
        e["target_dataset"] for e in lin.edges()}
    assert len(nodes) == 5

    assert lin._find_cycle() is None
