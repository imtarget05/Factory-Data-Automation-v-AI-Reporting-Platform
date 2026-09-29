"""
Data lineage — quan hệ RAW -> SILVER -> GOLD -> MART.

Mỗi edge ghi: source, target, transform, run_id, timestamp.
Truy vấn được hai chiều: upstream (ai tạo ra) và downstream (ai dùng).

Bất biến:
    * DAG không được cycle — edge tạo cycle thì raise
    * edge trùng (cùng source/target/transform) idempotent, không nhân bản
    * lưu JSON để process khác đọc lại được
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.catalog.registry import ZONE_ORDER, Catalog

DEFAULT_LINEAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "catalog", "lineage.json",
)


class LineageError(ValueError):
    """Edge không hợp lệ hoặc tạo cycle."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Lineage:
    """
    Đồ thị có hướng giữa các dataset, kèm metadata mỗi edge.

    Không dùng networkx: traversal trên vài chục node là đủ, và giữ
    dependency về 0 đáng giá cho một module lineage nhỏ.
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or DEFAULT_LINEAGE_PATH
        self._edges: dict[str, list[dict]] = {}
        if os.path.isfile(self.path):
            self.load()

    # -- ghi --------------------------------------------------------------
    def add_edge(self, source: str, target: str, transform: str,
                 run_id: str | None = None) -> dict:
        """
        Thêm edge source -> target.

        Idempotent: cùng (source, target, transform) trả về edge cũ.
        Cycle: nếu target đã nằm trên đường đi ngược từ source, raise.
        """
        if not source or not target:
            raise LineageError("source và target không được rỗng")
        if source == target:
            raise LineageError(f"tự vòng: {source} -> {target}")
        if self._reaches(source, target):
            raise LineageError(
                f"edge tạo cycle: {source} -> {target} (đã có đường đi ngược lại)")

        for e in self._edges.get(source, []):
            if e["target_dataset"] == target and e["transform"] == transform:
                return e  # idempotent

        edge = {
            "source_dataset": source,
            "target_dataset": target,
            "transform": transform,
            "run_id": run_id or f"run-{int(datetime.now(timezone.utc).timestamp())}",
            "timestamp": _now(),
        }
        self._edges.setdefault(source, []).append(edge)
        return edge

    def _reaches(self, src: str, dst: str) -> bool:
        """True nếu đã có đường dst -> ... -> src (thêm src->dst sẽ tạo cycle)."""
        seen: set[str] = set()
        stack = [dst]
        while stack:
            cur = stack.pop()
            if cur == src:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            for e in self._edges.get(cur, []):
                stack.append(e["target_dataset"])
        return False

    # -- đọc --------------------------------------------------------------
    def upstream(self, dataset: str) -> list[str]:
        """Dataset nào tạo ra dataset này (trực tiếp)."""
        return sorted({e["source_dataset"]
                       for es in self._edges.values() for e in es
                       if e["target_dataset"] == dataset})

    def downstream(self, dataset: str) -> list[str]:
        """Dataset này tạo ra dataset nào (trực tiếp)."""
        return sorted({e["target_dataset"] for e in self._edges.get(dataset, [])})

    def ancestors(self, dataset: str) -> list[str]:
        """Toàn bộ nguồn gốc, BFS ngược."""
        out: set[str] = set()
        stack = [dataset]
        while stack:
            for up in self.upstream(stack.pop()):
                if up not in out:
                    out.add(up)
                    stack.append(up)
        return sorted(out)
        return sorted(out)

    def descendants(self, dataset: str) -> list[str]:
        """Toàn bộ hậu duệ, BFS xuôi."""
        out: set[str] = set()
        stack = [dataset]
        while stack:
            for dn in self.downstream(stack.pop()):
                if dn not in out:
                    out.add(dn)
                    stack.append(dn)
        return sorted(out)

    def edges(self) -> list[dict]:
        """Tất cả edge, sắp theo (source, target, transform) — deterministic."""
        return sorted(
            (e for es in self._edges.values() for e in es),
            key=lambda e: (e["source_dataset"], e["target_dataset"], e["transform"]),
        )

    def graph(self) -> dict[str, list[str]]:
        return {k: self.downstream(k) for k in sorted(self._edges)}

    def _find_cycle(self) -> list[str] | None:
        """DFS có màu để phát hiện cycle trong graph đã có."""
        white, grey, black = 0, 1, 2
        color: dict[str, int] = {}
        # Tên hằng trong hàm: ruff N806 muốn lowercase. Hằng số thật sự
        # nên nằm ở module scope, nhưng chúng chỉ có ý nghĩa trong DFS này
        # nên giữ cục bộ và dùng chữ thường cho đúng quy ước.

        def visit(node: str, path: list[str]):
            color[node] = grey
            path.append(node)
            for nxt in self.downstream(node):
                c = color.get(nxt, white)
                if c == grey:
                    return path[path.index(nxt):] + [nxt]
                if c == white:
                    found = visit(nxt, path)
                    if found:
                        return found
            path.pop()
            color[node] = black
            return None

        for node in sorted(self._edges):
            if color.get(node, white) == white:
                found = visit(node, [])
                if found:
                    return found
        return None

    def has_cycle(self) -> bool:
        return self._find_cycle() is not None

    # -- lưu / đọc -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "lineage_version": "1.0",
            "generated_at": _now(),
            "zone_order": list(ZONE_ORDER),
            "edges": self.edges(),
        }

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def save(self, path: str | None = None) -> str:
        target = path or self.path
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(self.serialize())
            fh.write("\n")
        return target

    def load(self, path: str | None = None) -> None:
        target = path or self.path
        if not os.path.isfile(target):
            return
        with open(target, encoding="utf-8") as fh:
            raw = json.load(fh)
        self._edges = {}
        for e in raw.get("edges", []):
            self._edges.setdefault(e["source_dataset"], []).append(e)

    def build_from_catalog(self, catalog: Catalog, transform: str = "etl") -> None:
        """
        Suy ra edge từ trường `source` của catalog.

        Dùng để lineage không lệch với catalog — một nguồn sự thật.
        """
        for entry in catalog.list():
            for src in entry.source:
                self.add_edge(src, entry.name, transform, run_id="catalog-seed")

    def __len__(self) -> int:
        return sum(len(v) for v in self._edges.values())
