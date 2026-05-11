from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from interfaces.base_llm import BaseLLM, LLMResponseFormatError
from modules.llm.ollama_client import OllamaClient, OllamaConnectionError


class _FakeResponse:
    """urllib 응답 context manager를 흉내 내는 테스트 더블."""

    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


class OllamaClientTest(unittest.TestCase):
    """OllamaClient의 요청 처리와 JSON 파싱을 검증한다."""

    def setUp(self) -> None:
        self.client = OllamaClient()

    def test_ollama_is_available(self) -> None:
        """서버 상태 확인 요청이 성공하면 True를 반환한다."""
        with patch("urllib.request.urlopen", return_value=_FakeResponse({"models": []})):
            self.assertTrue(self.client.is_available())

    def test_generate_returns_nonempty_string(self) -> None:
        """간단한 프롬프트에 대해 비어있지 않은 응답을 반환한다."""
        with patch("urllib.request.urlopen", return_value=_FakeResponse({"response": "hello"})):
            response = self.client.generate("Say hello in one word.")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response.strip()), 0)

    def test_generate_json_returns_dict(self) -> None:
        """JSON 응답 프롬프트에 대해 딕셔너리를 반환한다."""
        prompt = 'Return ONLY this JSON, no explanation: {"status": "ok"}'
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"response": '{"status": "ok"}'}),
        ):
            result = self.client.generate_json(prompt, fallback={"status": "fallback"})
        self.assertIsInstance(result, dict)
        self.assertEqual("ok", result["status"])

    def test_generate_json_list_returns_list(self) -> None:
        """JSON 배열 응답 프롬프트에 대해 리스트를 반환한다."""
        prompt = 'Return ONLY this JSON array, no explanation: [{"name": "voltage"}]'
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"response": '[{"name": "voltage"}]'}),
        ):
            result = self.client.generate_json_list(prompt, fallback=[])
        self.assertIsInstance(result, list)
        self.assertEqual("voltage", result[0]["name"])

    def test_generate_json_fallback_on_invalid_response(self) -> None:
        """JSON 파싱이 불가능한 응답이 오면 fallback을 반환한다."""
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"response": "이건 JSON이 아닙니다"}),
        ):
            result = self.client.generate_json("return json", fallback={"status": "fallback"})
        self.assertEqual({"status": "fallback"}, result)

    def test_parse_json_extracts_from_code_block(self) -> None:
        """```json ... ``` 블록에서 JSON을 정확히 추출한다."""
        text = '```json\n{"match": true, "score": 0.9}\n```'
        result = BaseLLM.parse_json_response(text)
        self.assertEqual(result["match"], True)
        self.assertAlmostEqual(result["score"], 0.9)

    def test_parse_json_extracts_inline(self) -> None:
        """설명 텍스트 사이에 있는 JSON 블록을 추출한다."""
        text = '네, 맞습니다. {"match": true, "score": 0.85} 이것이 결과입니다.'
        result = BaseLLM.parse_json_response(text)
        self.assertEqual(result["match"], True)

    def test_parse_json_raises_for_plain_text(self) -> None:
        """JSON이 없는 텍스트는 LLMResponseFormatError를 발생시킨다."""
        with self.assertRaises(LLMResponseFormatError):
            BaseLLM.parse_json_response("이건 JSON이 아닙니다")

    def test_connection_error_on_wrong_url(self) -> None:
        """잘못된 주소로 연결 시 OllamaConnectionError가 발생한다."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(OllamaConnectionError):
                self.client.generate("test")

    def test_embed_returns_embedding_vector(self) -> None:
        """임베딩 응답에서 float 벡터를 반환한다."""
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse({"embedding": [0.1, 0.2, 0.3]}),
        ):
            result = self.client.embed("Rated Voltage")
        self.assertEqual([0.1, 0.2, 0.3], result)


if __name__ == "__main__":
    unittest.main()
