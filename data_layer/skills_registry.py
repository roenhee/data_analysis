from __future__ import annotations

import json

from data_layer.config import Config


def _registry_path(config: Config):
    return config.config_dir / "skills_registry.json"


def load_skills_registry(config: Config) -> list:
    """등록된 스킬 디스크립터 목록. 없으면 빈 리스트. ③이 카탈로그로 표시."""
    path = _registry_path(config)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def register_skill(config: Config, descriptor: dict) -> None:
    """스킬 디스크립터를 name 기준 upsert. ②가 스킬을 만들 때 호출."""
    config.ensure_dirs()
    reg = load_skills_registry(config)
    reg = [s for s in reg if s.get("name") != descriptor["name"]]
    reg.append(descriptor)
    _registry_path(config).write_text(json.dumps(reg, ensure_ascii=False, indent=2))
