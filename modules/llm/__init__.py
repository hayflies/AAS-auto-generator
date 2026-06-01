"""LLM 공통 인프라 패키지.

계층별 구현체는 각 기능 디렉토리에 둔다.

- `modules/extraction/llm_extractor.py`
- `modules/semantic_node/llm_semantic_builder.py`
- `modules/retrieval/embedding_retriever.py`
- `modules/matching/llm_matcher.py`
"""

from modules.llm.ollama_client import OllamaClient, OllamaConnectionError

__all__ = [
    "OllamaClient",
    "OllamaConnectionError",
]
