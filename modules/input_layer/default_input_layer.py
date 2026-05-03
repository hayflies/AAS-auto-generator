from __future__ import annotations

from typing import Any

from app.models import AssetPackage
from app.text import slugify
from interfaces.base_input import BaseInputLayer


class DefaultInputLayer(BaseInputLayer):
    """CLI/API 형태 payload를 안정적인 AssetPackage로 정규화한다.

    입력 채널별 차이는 이 계층에서 흡수하고, 이후 단계는 항상
    AssetPackage만 받도록 만드는 것이 역할이다.
    """

    def collect(self, payload: dict[str, Any]) -> AssetPackage:
        """payload에서 자산 기본 정보, 이미지, 문서, 사용자 입력을 수집한다."""

        # description.md 예시처럼 `raw_asset_package`로 감싸진 입력도 허용한다.
        raw = payload.get("raw_asset_package", payload)
        user_inputs = dict(raw.get("user_inputs") or {})

        asset_name = (
            raw.get("asset_name")
            or user_inputs.get("asset_name")
            or raw.get("name")
            or "Unnamed Asset"
        )
        asset_id = raw.get("asset_id") or user_inputs.get("asset_id") or slugify(asset_name)
        asset_type = raw.get("asset_type") or user_inputs.get("asset_type") or "unknown"

        manufacturer = raw.get("manufacturer") or user_inputs.get("manufacturer")
        model_name = raw.get("model_name") or user_inputs.get("model_name")

        # 입력 시스템마다 필드명이 다를 수 있어 대표 alias를 함께 처리한다.
        images = list(raw.get("images") or raw.get("asset_images") or [])
        documents = list(raw.get("documents") or raw.get("manual_files") or [])

        # downstream extractor가 user_inputs만 보더라도 핵심 식별 정보를 읽을 수 있게 보강한다.
        user_inputs.setdefault("asset_id", asset_id)
        user_inputs.setdefault("asset_name", asset_name)
        user_inputs.setdefault("asset_type", asset_type)
        if manufacturer is not None:
            user_inputs.setdefault("manufacturer", manufacturer)
        if model_name is not None:
            user_inputs.setdefault("model_name", model_name)

        return AssetPackage(
            asset_id=asset_id,
            asset_name=asset_name,
            asset_type=asset_type,
            manufacturer=manufacturer,
            model_name=model_name,
            images=images,
            documents=documents,
            user_inputs=user_inputs,
        )
