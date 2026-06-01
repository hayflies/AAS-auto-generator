from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from app.models import AASPropertyCandidate, SemanticNode
from app.text import normalize_label, tokenize
from interfaces.base_embedding import BaseEmbeddingModel
from interfaces.base_retriever import BaseCandidateRetriever
from modules.standards import CandidateSourceRegistry


MAX_EMBEDDING_TEXT_CHARS = 1200


class HybridStandardsCandidateRetriever(BaseCandidateRetriever):
    """Retrieves candidates from IDTA templates, ECLASS, and IEC CDD.

    When embeddings are available, candidates are ranked by cosine similarity only.
    Lexical scoring is kept as an offline fallback for runs without an embedding
    model. This keeps embedding-model comparisons from being biased by a lexical
    pre-filter or deterministic post-ranking rules.
    """

    def __init__(
        self,
        template_root: Path,
        eclass_path: Path,
        iec_cdd_path: Path,
        embedding_model: BaseEmbeddingModel | None = None,
        use_embeddings: bool = False,
        fail_on_embedding_error: bool = False,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.use_embeddings = use_embeddings and embedding_model is not None
        self.fail_on_embedding_error = fail_on_embedding_error
        self.progress_callback = progress_callback
        self._candidates = CandidateSourceRegistry(
            template_root=template_root,
            eclass_path=eclass_path,
            iec_cdd_path=iec_cdd_path,
        ).load_candidates()
        self._candidate_embedding_cache: dict[str, list[float] | None] = {}
        self._candidate_embedding_total = len(
            {candidate.candidate_id for candidate in self._candidates}
        )

    def retrieve(self, semantic_node: SemanticNode, top_k: int) -> list[AASPropertyCandidate]:
        if not self._candidates:
            return []

        query_text = self._node_text(semantic_node)
        if self.use_embeddings:
            return self._retrieve_by_embedding(semantic_node, query_text, top_k)

        return self._retrieve_by_lexical_fallback(semantic_node, query_text, top_k)

    def _retrieve_by_embedding(
        self,
        semantic_node: SemanticNode,
        query_text: str,
        top_k: int,
    ) -> list[AASPropertyCandidate]:
        try:
            query_embedding = self.embedding_model.embed(query_text)  # type: ignore[union-attr]
        except Exception as exc:
            if self.fail_on_embedding_error:
                raise
            print(f"[HybridRetriever] Embedding query failed, lexical fallback: {exc}")
            return self._retrieve_by_lexical_fallback(semantic_node, query_text, top_k)

        scored: list[tuple[AASPropertyCandidate, float]] = []
        for candidate in self._candidates:
            was_cached = candidate.candidate_id in self._candidate_embedding_cache
            candidate_embedding = self._candidate_embedding(candidate)
            if self.progress_callback and not was_cached:
                self.progress_callback(
                    "candidate embeddings",
                    len(self._candidate_embedding_cache),
                    self._candidate_embedding_total,
                )
            if candidate_embedding is None:
                continue
            score = _cosine_similarity(query_embedding, candidate_embedding)
            cloned = self._clone_candidate(candidate)
            cloned.similarity_score = score
            scored.append((cloned, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [candidate for candidate, _ in self._dedupe_ranked(scored)[:top_k]]

    def _retrieve_by_lexical_fallback(
        self,
        semantic_node: SemanticNode,
        query_text: str,
        top_k: int,
    ) -> list[AASPropertyCandidate]:
        query_tokens = tokenize(query_text)

        lexical_scored: list[tuple[int, AASPropertyCandidate, float]] = []
        for index, candidate in enumerate(self._candidates):
            lexical = self._lexical_score(query_tokens, semantic_node, candidate)
            lexical_scored.append((index, candidate, lexical))

        scored: list[tuple[AASPropertyCandidate, float]] = []
        for index, candidate, lexical in lexical_scored:
            score = self._rerank(lexical, semantic_node, candidate)
            cloned = self._clone_candidate(candidate)
            cloned.similarity_score = score
            scored.append((cloned, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [candidate for candidate, _ in self._dedupe_ranked(scored)[:top_k]]

    def _candidate_embedding(self, candidate: AASPropertyCandidate) -> list[float] | None:
        cached = self._candidate_embedding_cache.get(candidate.candidate_id)
        if cached is not None or candidate.candidate_id in self._candidate_embedding_cache:
            return cached
        try:
            cached = self.embedding_model.embed(self._candidate_text(candidate))  # type: ignore[union-attr]
        except Exception as exc:
            print(
                "[HybridRetriever] Candidate embedding skipped "
                f"({candidate.candidate_id}): {exc}"
            )
            cached = None
        self._candidate_embedding_cache[candidate.candidate_id] = cached
        return cached

    def _lexical_score(
        self,
        query_tokens: set[str],
        semantic_node: SemanticNode,
        candidate: AASPropertyCandidate,
    ) -> float:
        candidate_text = self._candidate_text(candidate)
        candidate_tokens = tokenize(candidate_text)
        if not query_tokens or not candidate_tokens:
            return 0.0

        intersection = query_tokens & candidate_tokens
        jaccard = len(intersection) / len(query_tokens | candidate_tokens)
        coverage = len(intersection) / len(query_tokens)

        node_name = normalize_label(semantic_node.name).lower()
        alias_score = 0.0
        for alias in candidate.aliases:
            alias_norm = normalize_label(alias).lower()
            if alias_norm == node_name:
                alias_score = 1.0
                break
            if _contains_meaningful_phrase(alias_norm, node_name):
                alias_score = max(alias_score, 0.65)

        id_short_norm = normalize_label(candidate.idShort).lower()
        if id_short_norm == node_name:
            alias_score = max(alias_score, 1.0)
        elif _contains_meaningful_phrase(id_short_norm, node_name):
            alias_score = max(alias_score, 0.65)

        score = min((jaccard * 0.35) + (coverage * 0.35) + (alias_score * 0.30), 1.0)
        if alias_score >= 1.0:
            score = max(score, 0.90)
        elif alias_score >= 0.65:
            score = max(score, 0.68)
        return score

    def _rerank(
        self,
        stage_one_score: float,
        semantic_node: SemanticNode,
        candidate: AASPropertyCandidate,
    ) -> float:
        if semantic_node.eclass_irdi and candidate.eclass_irdi == semantic_node.eclass_irdi:
            return _exact_identifier_score(candidate)
        if semantic_node.eclass_irdi and candidate.semantic_id == semantic_node.eclass_irdi:
            return _exact_identifier_score(candidate)

        score = stage_one_score
        score += min(candidate.source_priority, 1.0) * 0.10

        if semantic_node.unit and candidate.preferred_unit:
            if _same_unit(semantic_node.unit, candidate.preferred_unit):
                score += 0.10
            else:
                score -= 0.10

        if candidate.value_type and _compatible_value_type(semantic_node.value_type, candidate.value_type):
            score += 0.05

        if candidate.source == "submodel_template":
            score += 0.06

        return max(0.0, min(score, 0.97))

    def _node_text(self, semantic_node: SemanticNode) -> str:
        return _compact_embedding_text(
            " ".join(
                part
                for part in [
                    semantic_node.name,
                    semantic_node.conceptual_definition,
                    semantic_node.affordance,
                    semantic_node.unit or "",
                    semantic_node.eclass_irdi or "",
                ]
                if part
            )
        )

    def _candidate_text(self, candidate: AASPropertyCandidate) -> str:
        return _compact_embedding_text(
            " ".join(
                part
                for part in [
                    candidate.idShort,
                    _clip_text(candidate.description, 320),
                    _clip_text(candidate.definition or "", 320),
                    candidate.submodel,
                    candidate.path or "",
                    " ".join(candidate.aliases[:8]),
                    candidate.preferred_unit or "",
                    candidate.semantic_id or "",
                    candidate.eclass_irdi or "",
                ]
                if part
            )
        )

    def _dedupe_ranked(
        self,
        scored: list[tuple[AASPropertyCandidate, float]],
    ) -> list[tuple[AASPropertyCandidate, float]]:
        best: dict[tuple[str, str], tuple[AASPropertyCandidate, float]] = {}
        for candidate, score in scored:
            key = (candidate.submodel, candidate.idShort.lower())
            existing = best.get(key)
            if existing is None or score > existing[1]:
                best[key] = (candidate, score)
        return sorted(best.values(), key=lambda item: item[1], reverse=True)

    def _clone_candidate(self, candidate: AASPropertyCandidate) -> AASPropertyCandidate:
        return AASPropertyCandidate(**candidate.to_dict())


def _compact_embedding_text(text: str) -> str:
    compact = " ".join(str(text or "").split())
    return _clip_text(compact, MAX_EMBEDDING_TEXT_CHARS)


def _clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] or text[:max_chars]


def _contains_meaningful_phrase(a: str, b: str) -> bool:
    if not a or not b:
        return False
    shorter, longer = sorted([a, b], key=len)
    if len(shorter) <= 2:
        return False
    return shorter in longer


def _same_unit(left: str, right: str) -> bool:
    return _unit_key(left) == _unit_key(right)


def _unit_key(value: str) -> str:
    text = value.strip().lower().replace(" ", "")
    aliases = {
        "vdc": "v",
        "vac": "v",
        "volt": "v",
        "volts": "v",
        "ampere": "a",
        "amperes": "a",
        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",
        "degreecelsius": "degc",
        "celsius": "degc",
        "degc": "degc",
        "c": "degc",
        "rpm": "1/min",
        "r/min": "1/min",
        "min-1": "1/min",
    }
    return aliases.get(text, text)


def _compatible_value_type(node_type: str, candidate_type: str) -> bool:
    node = node_type.lower()
    candidate = candidate_type.lower()
    if node in {"float", "double", "integer", "int"}:
        return any(token in candidate for token in ["double", "float", "int", "decimal"])
    if node in {"boolean", "bool"}:
        return "bool" in candidate
    if node == "range":
        return "range" in candidate or any(token in candidate for token in ["double", "float", "int"])
    return "string" in candidate or "langstring" in candidate or "anyuri" in candidate


def _exact_identifier_score(candidate: AASPropertyCandidate) -> float:
    if candidate.source == "submodel_template" and candidate.submodel not in {
        "DigitalNameplate",
        "TechnicalData",
        "ProvisionOf3DModels",
        "OperationalData",
    }:
        return 0.965
    priority = {
        "submodel_template": 1.0,
        "iec_cdd_dictionary": 0.985,
        "eclass_dictionary": 0.98,
    }
    return priority.get(candidate.source, 0.97)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
