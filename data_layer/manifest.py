from __future__ import annotations

import json
from pathlib import Path


class Manifest:
    """캐시 색인. results/published/config 3개 섹션.

    표본 시대의 `events`·`dims` 섹션은 표본 경로와 함께 사라졌다. 큐브 parquet 은
    매니페스트가 아니라 `analytics/cube/store` 의 캐시 키 규약으로 색인한다.
    """

    def __init__(self, path: Path, data: dict):
        self.path = Path(path)
        self.data = data

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        path = Path(path)
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = {"results": [], "config": {}}
        for key in ("results", "published"):
            data.setdefault(key, [])
        data.setdefault("config", {})
        return cls(path, data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

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

    # --- published (스킬↔플랫폼 결과 색인) ---
    def add_published(
        self,
        id: str,
        run_id: str,
        skill: str,
        analysis_type: str,
        title: str,
        created_at: str,
        config_version: str,
        data_ref: str,
        envelope_ref: str,
    ) -> None:
        self.data["published"] = [
            p for p in self.data["published"] if p["id"] != id
        ]
        self.data["published"].append(
            {
                "id": id,
                "run_id": run_id,
                "skill": skill,
                "analysis_type": analysis_type,
                "title": title,
                "created_at": created_at,
                "config_version": config_version,
                "data_ref": data_ref,
                "envelope_ref": envelope_ref,
            }
        )

    def list_published(self, run_id: str | None = None) -> list:
        pubs = self.data["published"]
        if run_id is not None:
            return [p for p in pubs if p["run_id"] == run_id]
        return list(pubs)

    # --- top-level config 버전 ---
    def set_config(
        self,
        dictionary_version: str,
        sessionization_version: str,
        sources_version: str,
    ) -> None:
        self.data["config"] = {
            "dictionary_version": dictionary_version,
            "sessionization_version": sessionization_version,
            "sources_version": sources_version,
        }
