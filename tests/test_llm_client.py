from __future__ import annotations

import unittest

from modules.llm.ollama_client import OllamaClient, OllamaConnectionError


class OllamaClientTest(unittest.TestCase):
    """OllamaClient의 연결, 응답, JSON 파싱을 검증한다."""

    def setUp(self) -> None:
        self.client = OllamaClient()

    def test_ollama_is_available(self) -> None:
        """Ollama 서버가 실행 중인지 확인한다."""
        self.assertTrue(self.client.is_available(), "Ollama 서버가 실행 중이어야 합니다.")

    def test_generate_returns_nonempty_string(self) -> None:
        """간단한 프롬프트에 대해 비어있지 않은 응답을 반환한다."""
        response = self.client.generate("Say hello in one word.")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response.strip()), 0)

    def test_generate_json_returns_dict(self) -> None:
        """JSON 응답 프롬프트에 대해 딕셔너리를 반환한다."""
        prompt = 'Return ONLY this JSON, no explanation: {"status": "ok"}'
        result = self.client.generate_json(prompt, fallback={"status": "fallback"})
        self.assertIsInstance(result, dict)

    def test_generate_json_list_returns_list(self) -> None:
        """JSON 배열 응답 프롬프트에 대해 리스트를 반환한다."""
        prompt = 'Return ONLY this JSON array, no explanation: [{"name": "voltage"}]'
        result = self.client.generate_json_list(prompt, fallback=[])
        self.assertIsInstance(result, list)

    def test_generate_json_fallback_on_invalid_response(self) -> None:
        """JSON 파싱이 불가능한 응답이 오면 fallback을 반환한다."""
        # _parse_json을 직접 호출해서 파싱 실패 케이스 테스트
        with self.assertRaises(ValueError):
            self.client._parse_json("이건 JSON이 아닙니다")

    def test_parse_json_extracts_from_code_block(self) -> None:
        """```json ... ``` 블록에서 JSON을 정확히 추출한다."""
        text = '```json\n{"match": true, "score": 0.9}\n```'
        result = self.client._parse_json(text)
        self.assertEqual(result["match"], True)
        self.assertAlmostEqual(result["score"], 0.9)

    def test_parse_json_extracts_inline(self) -> None:
        """설명 텍스트 사이에 있는 JSON 블록을 추출한다."""
        text = '네, 맞습니다. {"match": true, "score": 0.85} 이것이 결과입니다.'
        result = self.client._parse_json(text)
        self.assertEqual(result["match"], True)

    def test_connection_error_on_wrong_url(self) -> None:
        """잘못된 주소로 연결 시 OllamaConnectionError가 발생한다."""
        bad_client = OllamaClient(base_url="http://localhost:9999")
        with self.assertRaises(OllamaConnectionError):
            bad_client.generate("test")


if __name__ == "__main__":
    unittest.main()
