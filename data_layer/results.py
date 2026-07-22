from __future__ import annotations

import datetime
import json

import pandas as pd

from data_layer.config import Config
from data_layer.manifest import Manifest
from data_layer.util import content_hash


def publish_result(
    config: Config,
    run_id: str,
    skill: str,
    analysis_type: str,
    title: str,
    data: pd.DataFrame,
    viz: dict,
    params: dict,
    config_version: str,
    insight: str | None = None,
    caveats: str | None = None,
    created_at: str | None = None,
) -> str:
    """분석 산출물 하나를 계약 형식으로 발행.

    <id>.parquet(데이터) + <id>.json(봉투)을 쓰고 매니페스트 published[]에 색인.
    id는 (run_id, analysis_type, title)로 결정적. ②가 호출한다.
    """
    config.ensure_dirs()
    rid = content_hash(run_id, analysis_type, title)
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    data_ref = f"{rid}.parquet"
    envelope_ref = f"{rid}.json"
    data.to_parquet(config.results_dir / data_ref)

    columns = [{"name": str(c), "type": str(data[c].dtype)} for c in data.columns]
    envelope = {
        "id": rid,
        "run_id": run_id,
        "skill": skill,
        "analysis_type": analysis_type,
        "title": title,
        "created_at": created_at,
        "params": params,
        "config_version": config_version,
        "data_ref": data_ref,
        "columns": columns,
        "viz": viz,
        "insight": insight,
        "caveats": caveats,
    }
    (config.results_dir / envelope_ref).write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, default=str)
    )

    m = Manifest.load(config.manifest_path)
    m.add_published(
        id=rid,
        run_id=run_id,
        skill=skill,
        analysis_type=analysis_type,
        title=title,
        created_at=created_at,
        config_version=config_version,
        data_ref=data_ref,
        envelope_ref=envelope_ref,
    )
    m.save()
    return rid


def list_results(config: Config, run_id: str | None = None) -> list:
    """발행된 결과의 색인 목록(매니페스트 published[]). ③이 호출한다."""
    return Manifest.load(config.manifest_path).list_published(run_id=run_id)


def read_result(config: Config, id: str) -> tuple[pd.DataFrame, dict]:
    """발행된 결과의 (데이터 DataFrame, 봉투 dict)를 반환. ③이 호출한다."""
    envelope = json.loads((config.results_dir / f"{id}.json").read_text())
    df = pd.read_parquet(config.results_dir / envelope["data_ref"])
    return df, envelope
