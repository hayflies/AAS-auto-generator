"""Ollama 로컬 LLM 호출 클라이언트.

이 모듈은 Ollama REST API와 통신하는 단일 창구다.
llm_extractor.py와 llm_matcher.py 둘 다 이 클라이언트를 통해 LLM을 호출한다.

사용 전제:
    - Ollama가 로컬에 설치되어 실행 중이어야 한다.
    - 기본 주소: http://localhost:11434
    - 기본 LLM 모델: qwen2.5:7b
    - 기본 임베딩 모델: mxbai-embed-large
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from interfaces.base_embedding import BaseEmbeddingModel
from interfaces.base_llm import BaseLLM, LLMConnectionError


OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_EMBED_MODEL = "mxbai-embed-large"
REQUEST_TIMEOUT = 120


class OllamaConnectionError(LLMConnectionError):
    """Ollama 서버에 연결할 수 없을 때 발생하는 예외."""


class OllamaClient(BaseLLM, BaseEmbeddingModel):
    """Ollama REST API 클라이언트.

    프롬프트를 받아 LLM 응답을 반환한다.
    JSON 파싱을 시도하고, 실패하면 원본 텍스트를 반환한다.

    Args:
        model: 사용할 Ollama 모델 이름. 기본값은 qwen2.5:7b.
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

    def generate(self, prompt: str, **kwargs: object) -> str:
        """프롬프트를 Ollama에 전송하고 텍스트 응답을 반환한다.

        Args:
            prompt: LLM에게 보낼 프롬프트 문자열.

        Returns:
            LLM의 응답 텍스트. 응답이 비어있으면 빈 문자열을 반환한다.

        Raises:
            OllamaConnectionError: Ollama 서버에 연결할 수 없을 때.
        """
        url = f"{self.base_url}/api/generate"
        payload_data: dict[str, object] = {
            "model": str(kwargs.get("model", self.model)),
            "prompt": prompt,
            "stream": bool(kwargs.get("stream", False)),
        }
        options = kwargs.get("options")
        if isinstance(options, dict):
            payload_data["options"] = options
        payload = json.dumps(payload_data).encode("utf-8")

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

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """텍스트를 임베딩 벡터로 변환한다.

        Ollama /api/embeddings 엔드포인트를 호출한다.
        model을 지정하지 않으면 mxbai-embed-large를 먼저 시도하고,
        실패하면 self.model(qwen2.5:7b)로 fallback한다.

        Args:
            text: 임베딩할 텍스트.
            model: 사용할 임베딩 모델. 기본값은 mxbai-embed-large.

        Returns:
            float 리스트 (임베딩 벡터).

        Raises:
            OllamaConnectionError: 서버에 연결할 수 없을 때.
            ValueError: 임베딩 응답이 비어있을 때.
        """
        embed_model = model or DEFAULT_EMBED_MODEL
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
