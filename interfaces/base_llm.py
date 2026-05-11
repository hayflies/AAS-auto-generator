"""LLM Adapter 인터페이스.

Semantic Node 보강, entity matching, 문서 추출 같은 단계에서 LLM을 붙일 때
특정 벤더 API에 직접 결합하지 않기 위한 최소 계약이다.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class LLMError(Exception):
    """LLM adapter 계층의 공통 예외."""


class LLMConnectionError(LLMError):
    """LLM provider에 연결할 수 없을 때 발생하는 예외."""


class LLMResponseFormatError(LLMError):
    """LLM 응답에서 기대한 구조를 파싱할 수 없을 때 발생하는 예외."""


class BaseLLM(ABC):
    """prompt 기반 텍스트 생성과 JSON 응답 파싱을 수행하는 LLM adapter 계약."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        """입력 prompt와 옵션을 받아 모델 응답 문자열을 반환한다."""
        raise NotImplementedError

    def generate_json(
        self,
        prompt: str,
        fallback: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> dict[str, Any]:
        """prompt 응답에서 JSON object를 파싱한다.

        연결 오류는 호출자가 fallback 정책을 결정할 수 있도록 전파하고,
        응답 형식 오류는 fallback으로 흡수한다.
        """
        if fallback is None:
            fallback = {}

        try:
            result = self.parse_json_response(self.generate(prompt, **kwargs))
        except LLMConnectionError:
            raise
        except Exception:
            return fallback
        return result if isinstance(result, dict) else fallback

    def generate_json_list(
        self,
        prompt: str,
        fallback: list[Any] | None = None,
        **kwargs: object,
    ) -> list[Any]:
        """prompt 응답에서 JSON array를 파싱한다."""
        if fallback is None:
            fallback = []

        try:
            result = self.parse_json_response(self.generate(prompt, **kwargs))
        except LLMConnectionError:
            raise
        except Exception:
            return fallback
        return result if isinstance(result, list) else fallback

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any] | list[Any]:
        """LLM 텍스트 응답에서 JSON object 또는 array를 추출한다.

        ```json ... ``` fenced block과 설명 텍스트 사이에 포함된 JSON을 모두
        허용한다.
        """
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            return json.loads(code_block.group(1).strip())

        json_block = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if json_block:
            return json.loads(json_block.group(1).strip())

        raise LLMResponseFormatError(f"JSON을 찾을 수 없습니다. 응답: {text[:200]}")
