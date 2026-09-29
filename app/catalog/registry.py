"""
Data catalog registry — machine-readable metadata cho từng dataset.

Đây là **lớp ④ Cataloging & Search** của Data Lake (Phần B DESIGN-BRIEF).
Trả lời được: dataset này là gì, ai sở hữu, schema ra sao, đến từ đâu,
ai tiêu thụ, còn "tươi" không.

Lưu JSON trên đĩa để process khác đọc được — không chỉ Python.
Không framework, không DB: một JSON file là đủ cho tầng này.

Zone hợp lệ: RAW -> SILVER -> GOLD -> MART (đúng thứ tự medallion).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

ZONE_ORDER = ("RAW", "SILVER", "GOLD", "MART")

DEFAULT_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "catalog", "catalog.json",
)

REQUIRED_FIELDS = ("name", "description", "owner", "zone", "source", "version")

# Tên gold dataset phải khớp CHÍNH XÁC với app.etl.gold.GOLD_DATASETS, nếu không
# lineage sẽ không nối liền được raw -> silver -> gold -> mart.
from app.etl.gold import GOLD_DATASETS  # noqa: E402


class CatalogError(ValueError):
    """Metadata sai cấu trúc hoặc vi phạm quy tắc zone."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatasetEntry:
    """Một dataset trong catalog."""

    __slots__ = ("name", "description", "owner", "schema", "zone", "source",
                 "consumers", "freshness_sla_hours", "version",
                 "created_at", "updated_at")

    def __init__(self, **kw: Any) -> None:
        for f in REQUIRED_FIELDS:
            if f not in kw or kw[f] in (None, ""):
                raise CatalogError(f"thiếu trường bắt buộc: {f}")
        if kw["zone"] not in ZONE_ORDER:
            raise CatalogError(
                f"zone '{kw['zone']}' không hợp lệ — chỉ chấp nhận {ZONE_ORDER}")
        self.name = str(kw["name"])
        self.description = str(kw["description"])
        self.owner = str(kw["owner"])
        self.zone = str(kw["zone"])
        self.source = list(kw["source"]) if isinstance(kw["source"], list) else [kw["source"]]
        self.version = str(kw["version"])
        self.schema = kw.get("schema") or {}
        self.consumers = list(kw.get("consumers") or [])
        self.freshness_sla_hours = kw.get("freshness_sla_hours")
        self.created_at = kw.get("created_at") or _now()
        self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "owner": self.owner, "schema": self.schema, "zone": self.zone,
            "source": self.source, "consumers": self.consumers,
            "freshness_sla_hours": self.freshness_sla_hours,
            "version": self.version,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DatasetEntry:
        return cls(**d)

    def update(self, **kw: Any) -> None:
        """Sửa một phần metadata; created_at giữ, updated_at nhích."""
        for k, v in kw.items():
            if k == "zone" and v not in ZONE_ORDER:
                raise CatalogError(f"zone '{v}' không hợp lệ")
            if k == "source" and not isinstance(v, list):
                v = [v]
            if k == "consumers":
                v = list(v)
            setattr(self, k, v)
        self.updated_at = _now()


class Catalog:
    """
    Registry dataset. JSON trên đĩa, đọc lại được bằng mọi process.

    Nguyên tắc:
        * register trùng tên -> raise (không âm thầm ghi đè)
        * update là đường để đổi metadata
        * serialize sort_keys nên output deterministic
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or DEFAULT_CATALOG_PATH
        self._entries: dict[str, DatasetEntry] = {}
        if os.path.isfile(self.path):
            self.load()

    def register(self, **kw: Any) -> DatasetEntry:
        entry = DatasetEntry(**kw)
        if entry.name in self._entries:
            raise CatalogError(
                f"dataset '{entry.name}' đã đăng ký — dùng update() để đổi metadata")
        self._entries[entry.name] = entry
        return entry

    def get(self, name: str) -> DatasetEntry:
        if name not in self._entries:
            known = ", ".join(sorted(self._entries)) or "(rỗng)"
            raise CatalogError(f"không tìm thấy dataset '{name}'. Đã biết: {known}")
        return self._entries[name]

    def has(self, name: str) -> bool:
        return name in self._entries

    def list(self, zone: str | None = None) -> list[DatasetEntry]:
        """Sắp theo zone medallion rồi theo tên — deterministic."""
        items = list(self._entries.values())
        if zone is not None:
            items = [e for e in items if e.zone == zone]
        return sorted(items, key=lambda e: (ZONE_ORDER.index(e.zone), e.name))

    def update(self, name: str, **kw: Any) -> DatasetEntry:
        entry = self.get(name)
        entry.update(**kw)
        return entry

    def remove(self, name: str) -> None:
        self.get(name)
        del self._entries[name]

    # -- kiểm tra ---------------------------------------------------------
    def validate(self) -> list[str]:
        """
        Kiểm toàn catalog, trả về danh sách lỗi (rỗng = hợp lệ).

        Không raise — để CI báo hết bao nhiêu lỗi thay vì dừng ở lỗi đầu.
        """
        problems: list[str] = []
        for name, e in self._entries.items():
            for f in REQUIRED_FIELDS:
                if getattr(e, f, None) in (None, ""):
                    problems.append(f"{name}: thiếu {f}")
            if e.zone not in ZONE_ORDER:
                problems.append(f"{name}: zone '{e.zone}' không hợp lệ")
            for src in e.source:
                if src not in self._entries:
                    problems.append(
                        f"{name}: source '{src}' chưa đăng ký trong catalog")
            for c in e.consumers:
                if c not in self._entries:
                    problems.append(
                        f"{name}: consumer '{c}' chưa đăng ký trong catalog")
        return problems

    # -- lưu / đọc -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "catalog_version": "1.0",
            "generated_at": _now(),
            "zone_order": list(ZONE_ORDER),
            "datasets": [e.to_dict() for e in self.list()],
        }

    def serialize(self) -> str:
        """JSON deterministic — sort_keys + indent cố định."""
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
        self._entries = {
            d["name"]: DatasetEntry.from_dict(d) for d in raw.get("datasets", [])
        }

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        """Cho phép set(cat) / 'x' in list(cat) — __contains__ một mình chưa đủ."""
        return iter(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries


def seed_default_catalog() -> Catalog:
    """
    Catalog tối thiểu cho pipeline hiện có: raw -> silver -> gold.
    Không khai báo mart vì marts chưa tồn tại — catalog không được
    quảng bá thứ chưa implement.
    """
    cat = Catalog(path=os.devnull)
    cat.register(
        name="raw_production", description="CSV tho tu MES",
        owner="manufacturing-data", zone="RAW", source=[], version="1.0.0",
        schema={"Date": "date", "Actual_Qty": "int", "Good_Qty": "int"},
    )
    cat.register(
        name="silver_production", description="Da clean + qua contract gate",
        owner="manufacturing-data", zone="SILVER", source=["raw_production"],
        version="1.0.0", consumers=GOLD_DATASETS,
        freshness_sla_hours=24,
    )
    for g in GOLD_DATASETS:
        cat.register(
            name=g, description=f"Gold curated: {g}",
            owner="manufacturing-data", zone="GOLD", source=["silver_production"],
            version="1.0.0", freshness_sla_hours=48,
        )
    return cat

