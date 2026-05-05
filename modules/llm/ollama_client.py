"""Ollama 로컬 LLM 호출 클라이언트.

이 모듈은 Ollama REST API와 통신하는 단일 창구다.
llm_extractor.py와 llm_matcher.py 둘 다 이 클라이언트를 통해 LLM을 호출한다.

사용 전제:
    - Ollama가 로컬에 설치되어 실행 중이어야 한다.
    - 기본 주소: http://localhost:11434
    - 기본 모델: llama3.2
"""

import json
import re
import urllib.request
import urllib.error


OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
REQUEST_TIMEOUT = 120


class OllamaConnectionError(Exception):
    """Ollama 서버에 연결할 수 없을 때 발생하는 예외."""
    pass


class OllamaClient:
    """Ollama REST API 클라이언트.

    프롬프트를 받아 LLM 응답을 반환한다.
    JSON 파싱을 시도하고, 실패하면 원본 텍스트를 반환한다.

    Args:
        model: 사용할 Ollama 모델 이름. 기본값은 llama3.2.
        base_url: Ollama 서버 주소. 기본값은 http://localhost:11434.
        timeout: 요청 타임아웃(초). 기본값은 120.

    Example:
        client = OllamaClient()
        response = client.generate("안녕하세요")
        print(response)
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = REQUEST_TIMEOUT,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        """프롬프트를 Ollama에 전송하고 텍스트 응답을 반환한다.

        Args:
            prompt: LLM에게 보낼 프롬프트 문자열.

        Returns:
            LLM의 응답 텍스트. 응답이 비어있으면 빈 문자열을 반환한다.

        Raises:
            OllamaConnectionError: Ollama 서버에 연결할 수 없을 때.
        """
        url = f"{self.base_url}/api/generate"
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                return data.get("response", "").strip()

        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Ollama 서버에 연결할 수 없습니다. "
                f"Ollama가 실행 중인지 확인하세요. (주소: {self.base_url})\n"
                f"원인: {e}"
            ) from e

    def generate_json(self, prompt: str, fallback: dict | None = None) -> dict:
        """프롬프트를 전송하고 JSON으로 파싱된 응답을 반환한다.

        LLM 응답에서 JSON 블록을 추출해 파싱한다.
        파싱에 실패하면 fallback을 반환한다.

        Args:
            prompt: LLM에게 보낼 프롬프트 문자열.
            fallback: JSON 파싱 실패 시 반환할 기본값. 기본값은 빈 딕셔너리.

        Returns:
            파싱된 딕셔너리 또는 fallback 값.
        """
        if fallback is None:
            fallback = {}

        try:
            raw_text = self.generate(prompt)
            return self._parse_json(raw_text)
        except OllamaConnectionError:
            raise
        except Exception:
            return fallback

    def generate_json_list(self, prompt: str, fallback: list | None = None) -> list:
        """프롬프트를 전송하고 JSON 배열로 파싱된 응답을 반환한다.

        Args:
            prompt: LLM에게 보낼 프롬프트 문자열.
            fallback: JSON 파싱 실패 시 반환할 기본값. 기본값은 빈 리스트.

        Returns:
            파싱된 리스트 또는 fallback 값.
        """
        if fallback is None:
            fallback = []

        try:
            raw_text = self.generate(prompt)
            result = self._parse_json(raw_text)
            if isinstance(result, list):
                return result
            return fallback
        except OllamaConnectionError:
            raise
        except Exception:
            return fallback

    def _parse_json(self, text: str) -> dict | list:
        """텍스트에서 JSON을 추출해 파싱한다.

        LLM이 JSON 외에 설명 텍스트를 함께 반환하는 경우를 처리한다.
        ```json ... ``` 블록이 있으면 그 안의 내용만 파싱한다.
        없으면 텍스트 전체에서 첫 번째 JSON 블록을 찾아 파싱한다.

        Args:
            text: LLM 응답 텍스트.

        Returns:
            파싱된 딕셔너리 또는 리스트.

        Raises:
            ValueError: JSON을 파싱할 수 없을 때.
        """
        # ```json ... ``` 블록 추출 시도
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            return json.loads(code_block.group(1).strip())

        # 텍스트에서 첫 번째 { } 또는 [ ] 블록 추출 시도
        json_block = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if json_block:
            return json.loads(json_block.group(1).strip())

        raise ValueError(f"JSON을 찾을 수 없습니다. 응답: {text[:200]}")

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """텍스트를 임베딩 벡터로 변환한다.

        Ollama /api/embeddings 엔드포인트를 호출한다.
        model을 지정하지 않으면 nomic-embed-text를 먼저 시도하고,
        실패하면 self.model(llama3.2)로 fallback한다.

        Args:
            text: 임베딩할 텍스트.
            model: 사용할 임베딩 모델. 기본값은 nomic-embed-text.

        Returns:
            float 리스트 (임베딩 벡터).

        Raises:
            OllamaConnectionError: 서버에 연결할 수 없을 때.
            ValueError: 임베딩 응답이 비어있을 때.
        """
        embed_model = model or "nomic-embed-text"
        url = f"{self.base_url}/api/embeddings"
        payload = json.dumps({
            "model": embed_model,
            "prompt": text,
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
                embedding = data.get("embedding", [])
                if not embedding:
                    raise ValueError(f"임베딩 응답이 비어있습니다. 모델: {embed_model}")
                return embedding
        except urllib.error.HTTPError:
            # nomic-embed-text가 없으면 기본 모델로 재시도
            if embed_model != self.model:
                return self.embed(text, model=self.model)
            raise
        except urllib.error.URLError as e:
            raise OllamaConnectionError(
                f"Ollama 서버에 연결할 수 없습니다. (주소: {self.base_url})\n원인: {e}"
            ) from e

    def is_available(self) -> bool:
        """Ollama 서버가 실행 중인지 확인한다.

        Returns:
            서버가 응답하면 True, 아니면 False.
        """
        try:
            url = f"{self.base_url}/api/tags"
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=5):
                return True
        except Exception:
            return False
