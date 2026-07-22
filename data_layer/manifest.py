from __future__ import annotations

import json
from pathlib import Path


class Manifest:
    """캐시 색인. events/dims/results/config 4개 섹션."""

    def __init__(self, path: Path, data: dict):
        self.path = Path(path)
        self.data = data

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        path = Path(path)
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"events": [], "dims": [], "results": [], "config": {}}
        for key in ("events", "dims", "results"):
            data.setdefault(key, [])
        data.setdefault("config", {})
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    # --- events ---
    def event_start_days(self) -> set[str]:
        return {e["start_day"] for e in self.data["events"]}

    def has_event(self, source_id: str, start_day: str, source_query_hash: str) -> bool:
        return any(
            e["start_day"] == start_day
            and e["source_id"] == source_id
            and e["source_query_hash"] == source_query_hash
            for e in self.data["events"]
        )

    def add_event_partition(
        self,
        start_day: str,
        entities: int,
        rows: int,
        size_bytes: int,
        source_id: str,
        source_query_hash: str,
        sample: dict,
        window_bounds: list,
    ) -> None:
        self.data["events"] = [
            e for e in self.data["events"]
            if not (e["start_day"] == start_day and e["source_id"] == source_id)
        ]
        self.data["events"].append(
            {
                "start_day": start_day,
                "entities": entities,
                "rows": rows,
                "size_bytes": size_bytes,
                "source_id": source_id,
                "source_query_hash": source_query_hash,
                "sample": sample,
                "window_bounds": window_bounds,
            }
        )

    # --- results ---
    def has_result(self, result_hash: str) -> bool:
        return any(r["hash"] == result_hash for r in self.data["results"])

    def add_result(
        self,
        result_hash: str,
        source_summary: str,
        date_range: list,
        params: dict,
        config_version: str,
        rows: int,
        size_bytes: int,
    ) -> None:
        self.data["results"] = [
            r for r in self.data["results"] if r["hash"] != result_hash
        ]
        self.data["results"].append(
            {
                "hash": result_hash,
                "source_summary": source_summary,
                "date_range": date_range,
                "params": params,
                "config_version": config_version,
                "rows": rows,
                "size_bytes": size_bytes,
            }
        )

    # --- dims ---
    def add_dim(self, name: str, source_id: str, key: str, rows: int) -> None:
        self.data["dims"] = [d for d in self.data["dims"] if d["name"] != name]
        self.data["dims"].append(
            {"name": name, "source_id": source_id, "key": key, "rows": rows}
        )
