"""정보 추출 계층 인터페이스.

OCR, 문서 파서, LLM extractor, 수동 입력 정규화기를 같은 출력 계약으로 묶어
아래 단계가 추출 방식에 의존하지 않게 한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import AssetPackage, CVOutput, ExtractedEntity


class BaseInformationExtractor(ABC):
    """AssetPackage에서 raw entity 목록을 추출하는 계약."""

    @abstractmethod
    def extract(
        self,
        asset_package: AssetPackage,
        cv_output: CVOutput | None = None,
    ) -> list[ExtractedEntity]:
        """원천 입력과 선택 CV 결과를 바탕으로 ExtractedEntity 목록을 만든다."""
        raise NotImplementedError
