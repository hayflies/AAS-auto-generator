from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import AssetPackage
from app.text import slugify
from interfaces.base_input import BaseInputLayer
from modules.input_layer.document_processor import DocumentProcessor

# 문서 처리가 필요한 파일 확장자
_PROCESSABLE_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"
}


class DefaultInputLayer(BaseInputLayer):
    """CLI/API 형태 payload를 안정적인 AssetPackage로 정규화한다.

    입력 채널별 차이는 이 계층에서 흡수하고, 이후 단계는 항상
    AssetPackage만 받도록 만드는 것이 역할이다.

    PDF / 이미지 경로가 documents에 포함되어 있으면 DocumentProcessor로
    텍스트를 추출해서 AssetPackage.documents에 텍스트로 넣는다.
    """

    def __init__(self, processor: DocumentProcessor | None = None):
        """
        Args:
            processor: DocumentProcessor 인스턴스.
                       None이면 기본 인스턴스를 생성한다.
                       문서 처리를 완전히 끄려면 False를 전달한다 (테스트용 비권장).
        """
        self._processor = processor if processor is not None else DocumentProcessor()

    def collect(self, payload: dict[str, Any]) -> AssetPackage:
        """payload에서 자산 기본 정보, 이미지, 문서, 사용자 입력을 수집한다."""

        # description.md 예시처럼 `raw_asset_package`로 감싸진 입력도 허용한다.
        raw = payload.get("raw_asset_package", payload)
        user_inputs = dict(raw.get("user_inputs") or {})

        asset_name = (
            raw.get("asset_name")
            or user_inputs.get("asset_name")
            or raw.get("name")
            or user_inputs.get("manufacturer_product_designation")
            or user_inputs.get("manufacturer_product_family")
            or user_inputs.get("brand")
            or user_inputs.get("manufacturer_name")
            or "Unnamed Asset"
        )
        asset_id = raw.get("asset_id") or user_inputs.get("asset_id") or slugify(asset_name)
        asset_type = raw.get("asset_type") or user_inputs.get("asset_type") or "unknown"

        manufacturer = raw.get("manufacturer") or user_inputs.get("manufacturer")
        model_name = raw.get("model_name") or user_inputs.get("model_name")

        # 입력 시스템마다 필드명이 다를 수 있어 대표 alias를 함께 처리한다.
        images = list(raw.get("images") or raw.get("asset_images") or [])
        raw_documents = self._document_inputs(raw)
        raw_documents.extend(self._free_text_inputs(raw))

        # PDF / 이미지 경로는 텍스트로 변환한다. 이미 텍스트인 항목은 그대로 유지한다.
        documents = self._process_documents(raw_documents)

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

    def _free_text_inputs(self, raw: dict[str, Any]) -> list[str]:
        """사용자가 payload에 직접 넣은 임의 텍스트 입력을 문서 텍스트로 흡수한다."""
        text_values: list[str] = []
        for key in ("text", "input_text", "free_text", "manual_text", "user_text", "raw_text"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                text_values.append(value.strip())
            elif isinstance(value, list):
                text_values.extend(str(item).strip() for item in value if str(item).strip())
        return text_values

    def _document_inputs(self, raw: dict[str, Any]) -> list[str]:
        """매뉴얼/PDF 입력 alias를 모두 documents 입력으로 수집한다."""
        documents: list[str] = []
        for key in (
            "documents",
            "manual_files",
            "manual_pdfs",
            "user_manuals",
            "pdf_files",
            "datasheets",
            "specification_files",
        ):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                documents.append(value.strip())
            elif isinstance(value, (list, tuple)):
                documents.extend(str(item).strip() for item in value if str(item).strip())
        return documents

    def _process_documents(self, raw_documents: list) -> list:
        """문서 목록을 순회하며 파일 경로는 텍스트로 변환하고, 텍스트는 그대로 유지한다.

        - 파일 경로(.pdf, .jpg 등)인 항목 → DocumentProcessor로 텍스트 추출
        - 이미 텍스트인 항목 → 그대로 반환
        - 변환 실패 항목 → strict 모드에서는 예외, fallback 모드에서는 건너뜀
        """
        processed: list[str] = []

        for item in raw_documents:
            if not isinstance(item, str):
                continue

            ext = Path(item).suffix.lower()
            if ext in _PROCESSABLE_EXTENSIONS:
                text = self._processor.process(item)
                if text.strip():
                    processed.append(text)
                else:
                    print(f"[DefaultInputLayer] 문서 변환 결과 없음, 건너뜀: {item}")
            else:
                # 이미 텍스트이거나 알 수 없는 형식 → 그대로 사용
                processed.append(item)

        return processed
