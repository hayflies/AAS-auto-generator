"""sentence-transformers 기반 의미 AAS 매퍼.

DefaultAASMapper는 properties.json에 하드코딩된 submodel 필드를 그대로 쓴다.
SemanticAASMapper는 sentence-transformers로 각 속성의 의미와
서브모델 설명의 유사도를 계산해 더 정확하게 배치한다.

설치:
    pip install sentence-transformers
    # AMD GPU(RX9070XT) ROCm 지원:
    pip install torch --index-url https://download.pytorch.org/whl/rocm6.1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import AssetPackage, MatchedProperty, ModelInfo
from interfaces.base_mapper import BaseAASMapper

# 기본 sentence-transformers 모델 (경량, 영어 최적화)
_DEFAULT_MODEL = "all-MiniLM-L6-v2"

# 서브모델별 의미 설명 — 임베딩 쿼리로 사용
_SUBMODEL_DESCRIPTIONS = {
    "DigitalNameplate": (
        "identity manufacturer serial number product designation brand label nameplate"
    ),
    "TechnicalData": (
        "technical specifications voltage current weight dimensions power frequency temperature"
    ),
    "ProvisionOf3DModels": (
        "3D model file reference geometry shape visualization CAD"
    ),
    "OperationalData": (
        "sensor values real-time operational measurement runtime status monitoring"
    ),
}


class SemanticAASMapper(BaseAASMapper):
    """sentence-transformers로 속성을 서브모델에 의미 기반 배치한다.

    Args:
        template_path: default_submodels.json 경로.
        model_name: sentence-transformers 모델 이름.
                    기본값: 'all-MiniLM-L6-v2' (경량, 빠름).
    """

    def __init__(
        self,
        template_path: Path,
        model_name: str = _DEFAULT_MODEL,
    ) -> None:
        self.template_path = template_path
        self.model_name = model_name
        self.submodel_ids = self._load_submodel_ids(template_path)

        # sentence-transformers 로드 (선택적 의존성)
        self._st_model = self._load_st_model(model_name)

        # 서브모델 설명 임베딩 사전 계산 (초기화 시 1회)
        self._submodel_embeddings: dict[str, list[float]] = {}
        if self._st_model is not None:
            self._submodel_embeddings = self._precompute_submodel_embeddings()

    # ------------------------------------------------------------------ #
    # BaseAASMapper 구현
    # ------------------------------------------------------------------ #

    def map(
        self,
        asset_package: AssetPackage,
        matched_properties: list[MatchedProperty],
        model_info: ModelInfo,
    ) -> dict[str, Any]:
        """매칭 결과와 3D 모델 정보를 AAS Mapping Plan으로 변환한다.

        sentence-transformers가 사용 가능하면 의미 유사도로 서브모델을 결정한다.
        사용 불가능하면 기존 candidate.submodel 값을 그대로 사용한다.
        """
        submodels: dict[str, dict] = {
            sid: {"idShort": sid, "properties": []}
            for sid in self.submodel_ids
        }

        # 매칭 점수가 너무 낮은 항목 제외 (OCR 노이즈 오매핑 방지)
        _MIN_SCORE = 0.70

        # HandoverDocumentation 속성은 출력 서브모델 템플릿에 없으므로 제외
        _EXCLUDED_SUBMODELS = {"HandoverDocumentation"}

        for item in matched_properties:
            if item.match_score < _MIN_SCORE:
                continue
            if item.submodel in _EXCLUDED_SUBMODELS:
                continue

            # properties.json submodel 우선, 템플릿 없는 서브모델만 ST 재분류
            target_submodel = self._decide_submodel(item)

            submodel = submodels.setdefault(
                target_submodel,
                {"idShort": target_submodel, "properties": []},
            )

            # 같은 idShort가 이미 있으면 score가 더 높을 때만 교체 (중복 방지)
            existing = next(
                (p for p in submodel["properties"] if p["idShort"] == item.idShort),
                None,
            )
            new_entry = {
                "semantic_node_id": item.semantic_node_id,
                "aas_property_id": item.aas_property_id,
                "idShort": item.idShort,
                "value": item.value,
                "unit": item.unit,
                "match_score": item.match_score,
                "semanticId": item.semantic_id,
            }
            if existing is None:
                submodel["properties"].append(new_entry)
            elif item.match_score > existing["match_score"]:
                submodel["properties"].remove(existing)
                submodel["properties"].append(new_entry)

        # 3D 모델 참조 정보는 항상 ProvisionOf3DModels에 고정
        submodels.setdefault(
            "ProvisionOf3DModels",
            {"idShort": "ProvisionOf3DModels", "properties": []},
        )
        submodels["ProvisionOf3DModels"]["properties"].extend([
            {
                "semantic_node_id": None,
                "aas_property_id": "AAS_PROP_MODEL_PATH",
                "idShort": "ModelFile",
                "value": model_info.model_path,
                "unit": None,
                "match_score": 1.0,
                "semanticId": "https://admin-shell.io/idta/3d/ModelFile/1/0",
            },
            {
                "semantic_node_id": None,
                "aas_property_id": "AAS_PROP_MODEL_FORMAT",
                "idShort": "ModelFormat",
                "value": model_info.model_format,
                "unit": None,
                "match_score": 1.0,
                "semanticId": "https://admin-shell.io/idta/3d/ModelFormat/1/0",
            },
            {
                "semantic_node_id": None,
                "aas_property_id": "AAS_PROP_MODEL_GENERATION_METHOD",
                "idShort": "GenerationMethod",
                "value": model_info.generation_method,
                "unit": None,
                "match_score": 1.0,
                "semanticId": "https://example.org/aas/3d/GenerationMethod",
            },
        ])

        return {
            "asset": asset_package.to_dict(),
            "submodels": list(submodels.values()),
            "model_info": model_info.to_dict(),
        }

    # ------------------------------------------------------------------ #
    # 내부 구현
    # ------------------------------------------------------------------ #

    def _decide_submodel(self, item: MatchedProperty) -> str:
        """속성 하나에 가장 적합한 서브모델을 결정한다.

        우선순위:
        1. properties.json의 submodel 필드가 템플릿에 있으면 그대로 사용 (가장 정확).
        2. 템플릿에 없는 서브모델 (e.g. HandoverDocumentation)은
           ST 모델로 가장 가까운 템플릿 서브모델을 찾는다.
        3. ST 모델 없으면 DigitalNameplate로 fallback.

        sentence-transformers가 전체 재분류를 하면 오히려 오배치가 발생하므로
        properties.json의 명시적 submodel 값을 최우선으로 신뢰한다.
        """
        # ── 1. properties.json submodel이 템플릿에 있으면 그대로 사용 ──
        if item.submodel in self.submodel_ids:
            return item.submodel

        # ── 2. 템플릿에 없는 서브모델 → ST로 가장 가까운 것 찾기 ────────
        if self._st_model and self._submodel_embeddings:
            query = f"{item.idShort} {item.aas_property_id}"
            if item.semantic_id:
                query += f" {item.semantic_id.split('/')[-1]}"
            try:
                query_embedding = self._st_model.encode(query, convert_to_numpy=True)
                best_submodel = "DigitalNameplate"
                best_score = -1.0
                for submodel_id, sub_emb in self._submodel_embeddings.items():
                    if submodel_id == "ProvisionOf3DModels":
                        continue
                    score = self._cosine(query_embedding, sub_emb)
                    if score > best_score:
                        best_score = score
                        best_submodel = submodel_id
                return best_submodel
            except Exception as e:
                print(f"[SemanticAASMapper] 의미 매핑 실패, fallback 사용: {e}")

        # ── 3. Fallback ────────────────────────────────────────────────
        return "DigitalNameplate"

    def _precompute_submodel_embeddings(self) -> dict[str, list[float]]:
        """서브모델 설명 텍스트의 임베딩을 미리 계산해 캐싱한다."""
        embeddings: dict[str, list[float]] = {}
        for sid in self.submodel_ids:
            desc = _SUBMODEL_DESCRIPTIONS.get(sid, sid)
            try:
                emb = self._st_model.encode(desc, convert_to_numpy=True)
                embeddings[sid] = emb
            except Exception as e:
                print(f"[SemanticAASMapper] 서브모델 임베딩 실패 ({sid}): {e}")
        return embeddings

    def _cosine(self, a: Any, b: Any) -> float:
        """두 벡터의 코사인 유사도를 계산한다."""
        try:
            import numpy as np
            a = np.array(a, dtype=float)
            b = np.array(b, dtype=float)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except ImportError:
            # numpy 없으면 순수 Python 계산
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

    def _load_st_model(self, model_name: str):
        """sentence-transformers 모델을 로드한다.

        미설치이면 None을 반환하고 경고를 출력한다. (예외 전파 안 함)
        """
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

            print(f"[SemanticAASMapper] sentence-transformers 로드 중 (device={device})...")
            model = SentenceTransformer(model_name, device=device)
            print(f"[SemanticAASMapper] 모델 로드 완료: {model_name}")
            return model

        except ImportError:
            print(
                "[SemanticAASMapper] sentence-transformers 미설치. 기존 submodel 필드를 사용합니다.\n"
                "  설치: pip install sentence-transformers"
            )
            return None
        except Exception as e:
            print(f"[SemanticAASMapper] 모델 로드 실패, fallback 사용: {e}")
            return None

    def _load_submodel_ids(self, template_path: Path) -> list[str]:
        """Submodel template JSON에서 idShort 목록만 추출한다."""
        with template_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [item["idShort"] for item in data.get("submodels", [])]
