"""PDF 및 이미지 문서를 텍스트로 변환하고 LLM으로 정제하는 모듈.

지원 형식:
    - PDF  : pdfplumber 사용
    - 이미지: easyocr 사용 (JPG, PNG, BMP, TIFF 등)

두 라이브러리 모두 선택적 의존성이다. strict/fail-fast 실행에서는 설치나 추출 실패를
예외로 올려 파이프라인을 중단하고, fallback 실행에서만 경고 후 빈 결과를 반환한다.

설치 방법:
    pip install pdfplumber easyocr
    # AMD GPU (RX9070XT) ROCm 지원:
    pip install torch --index-url https://download.pytorch.org/whl/rocm6.1
"""

from __future__ import annotations

import os
from pathlib import Path

from interfaces.base_llm import BaseLLM
from modules.llm.ollama_client import OllamaClient
from modules.llm.prompts import build_text_cleaning_prompt

# 지원하는 이미지 확장자
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


class DocumentProcessor:
    """PDF / 이미지를 텍스트로 변환하고 LLM으로 정제한다.

    Args:
        client: BaseLLM 인스턴스. 기본값은 새 OllamaClient 인스턴스.
        ocr_languages: easyocr 언어 목록. 기본값 ['en'] (영문 명판).
        skip_llm_cleaning: True이면 LLM 정제 단계를 건너뛴다 (테스트용).
        fail_fast: True이면 LLM 정제 실패 시 원문 fallback 대신 예외를 전파한다.
    """

    def __init__(
        self,
        client: BaseLLM | None = None,
        ocr_languages: list[str] | None = None,
        skip_llm_cleaning: bool = False,
        fail_fast: bool = False,
        max_llm_cleaning_chars: int = 12000,
    ):
        self.client = client or OllamaClient()
        self.ocr_languages = ocr_languages or ["en"]
        self.skip_llm_cleaning = skip_llm_cleaning
        self.fail_fast = fail_fast
        self.max_llm_cleaning_chars = max_llm_cleaning_chars
        self._ocr_reader = None  # lazy init (easyocr 모델 로딩이 느림)

    # ------------------------------------------------------------------ #
    # 공개 API
    # ------------------------------------------------------------------ #

    def process(self, path: str) -> str:
        """파일 경로를 받아 정제된 텍스트를 반환한다.

        확장자에 따라 PDF / 이미지 처리를 자동으로 분기한다.
        지원하지 않는 형식이면 빈 문자열을 반환한다.
        """
        ext = Path(path).suffix.lower()

        if ext == ".pdf":
            return self.process_pdf(path)
        elif ext in _IMAGE_EXTENSIONS:
            return self.process_image(path)
        else:
            print(f"[DocumentProcessor] 지원하지 않는 형식: {ext} ({path})")
            return ""

    def process_pdf(self, pdf_path: str) -> str:
        """PDF 파일에서 텍스트를 추출하고 LLM으로 정제한다."""
        raw_text = self._extract_pdf_text(pdf_path)
        if not raw_text.strip():
            message = f"[DocumentProcessor] PDF에서 텍스트를 추출하지 못함: {pdf_path}"
            if self.fail_fast:
                raise RuntimeError(message)
            print(message)
            return ""
        return self._clean_with_llm(raw_text) if not self.skip_llm_cleaning else raw_text

    def process_image(self, image_path: str) -> str:
        """이미지 파일에서 OCR로 텍스트를 추출하고 LLM으로 정제한다."""
        raw_text = self._extract_image_text(image_path)
        if not raw_text.strip():
            print(f"[DocumentProcessor] 이미지에서 텍스트를 추출하지 못함: {image_path}")
            return ""
        return self._clean_with_llm(raw_text) if not self.skip_llm_cleaning else raw_text

    # ------------------------------------------------------------------ #
    # 내부 구현
    # ------------------------------------------------------------------ #

    def _extract_pdf_text(self, pdf_path: str) -> str:
        """pdfplumber로 PDF 본문과 표를 페이지 단위 provenance와 함께 추출한다."""
        if not Path(pdf_path).exists():
            message = f"[DocumentProcessor] PDF 파일이 존재하지 않습니다: {pdf_path}"
            if self.fail_fast:
                raise FileNotFoundError(message)
            print(message)
            return ""

        try:
            import pdfplumber  # type: ignore
        except ImportError:
            return self._extract_pdf_text_with_pypdf(pdf_path)

        try:
            lines: list[str] = []
            with pdfplumber.open(pdf_path) as pdf:
                lines.append(f"[PDF_FILE] {os.path.basename(pdf_path)}")
                for page_index, page in enumerate(pdf.pages, start=1):
                    try:
                        text = self._page_text(page)
                        if text:
                            lines.append(f"[PDF_PAGE {page_index}]\n{text.strip()}")
                        for table_index, table in enumerate(page.extract_tables() or [], start=1):
                            formatted_table = self._format_pdf_table(table)
                            if formatted_table:
                                lines.append(
                                    f"[PDF_TABLE {page_index}.{table_index}]\n{formatted_table}"
                                )
                    except Exception as page_error:
                        if self.fail_fast:
                            raise RuntimeError(
                                f"[DocumentProcessor] PDF page {page_index} 처리 오류: {page_error}"
                            ) from page_error
                        print(f"[DocumentProcessor] PDF page {page_index} 처리 오류: {page_error}")
            return "\n\n".join(lines)
        except Exception as e:
            if self.fail_fast:
                raise RuntimeError(f"[DocumentProcessor] PDF 처리 오류: {e}") from e
            print(f"[DocumentProcessor] PDF 처리 오류: {e}")
            return ""

    def _extract_pdf_text_with_pypdf(self, pdf_path: str) -> str:
        """pypdf fallback for environments without pdfplumber table extraction."""

        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            message = (
                "[DocumentProcessor] PDF 텍스트 추출 라이브러리가 없습니다.\n"
                "  설치: pip install pdfplumber 또는 pip install pypdf"
            )
            if self.fail_fast:
                raise ImportError(message)
            print(message)
            return ""

        try:
            reader = PdfReader(pdf_path)
            lines = [f"[PDF_FILE] {os.path.basename(pdf_path)}"]
            for page_index, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    lines.append(f"[PDF_PAGE {page_index}]\n{text.strip()}")
            return "\n\n".join(lines)
        except Exception as exc:
            if self.fail_fast:
                raise RuntimeError(f"[DocumentProcessor] pypdf PDF 처리 오류: {exc}") from exc
            print(f"[DocumentProcessor] pypdf PDF 처리 오류: {exc}")
            return ""

    @staticmethod
    def _page_text(page: object) -> str:
        """pdfplumber page에서 가능한 한 레이아웃을 보존해 텍스트를 추출한다."""
        try:
            text = page.extract_text(layout=True)  # type: ignore[attr-defined]
        except TypeError:
            text = page.extract_text()  # type: ignore[attr-defined]
        if text:
            return str(text)
        fallback = page.extract_text()  # type: ignore[attr-defined]
        return str(fallback or "")

    @staticmethod
    def _format_pdf_table(table: list[list[object]]) -> str:
        """PDF 표를 LLM이 읽기 쉬운 pipe-separated 텍스트로 변환한다."""
        rows: list[str] = []
        for row in table:
            cells = [str(cell or "").strip().replace("\n", " ") for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def _extract_image_text(self, image_path: str) -> str:
        """easyocr로 이미지에서 텍스트를 추출한다."""
        try:
            import easyocr  # type: ignore
        except ImportError:
            print(
                "[DocumentProcessor] easyocr가 설치되어 있지 않습니다.\n"
                "  설치: pip install easyocr\n"
                "  AMD GPU(ROCm): pip install torch --index-url https://download.pytorch.org/whl/rocm6.1"
            )
            return ""

        try:
            if self._ocr_reader is None:
                # GPU 사용 여부 자동 감지 (CUDA/ROCm 모두 torch.cuda로 노출됨)
                try:
                    import torch
                    gpu = torch.cuda.is_available()
                except ImportError:
                    gpu = False

                self._ocr_reader = easyocr.Reader(self.ocr_languages, gpu=gpu)

            # OpenCV가 한글 경로를 못 읽는 문제 우회:
            # 파일 경로 대신 numpy 배열로 직접 로딩해서 easyocr에 넘긴다.
            try:
                import numpy as np
                from PIL import Image as PILImage
                img_array = np.array(PILImage.open(image_path).convert("RGB"))
            except ImportError:
                img_array = image_path  # PIL 없으면 경로 직접 전달

            # detail=1: 좌표 정보 포함해서 읽기 → 라벨-값 행 매핑에 사용
            results = self._ocr_reader.readtext(img_array, detail=1)
            return self._pair_label_value(results)
        except Exception as e:
            print(f"[DocumentProcessor] 이미지 OCR 오류: {e}")
            return ""

    def _pair_label_value(self, results: list) -> str:
        """easyocr detail=1 결과를 좌표 기반으로 라벨:값 형태로 변환한다.

        같은 행(y 좌표 유사)의 텍스트를 묶고, x 좌표 순서로 정렬해
        "라벨: 값" 형태의 구조화된 텍스트를 반환한다.

        Args:
            results: easyocr detail=1 결과 [(bbox, text, confidence), ...]
        """
        if not results:
            return ""

        # bbox 중심 y 좌표 계산
        rows: list[tuple[float, float, str]] = []
        for bbox, text, conf in results:
            if conf < 0.3:  # 신뢰도 낮은 건 제외
                continue
            ys = [pt[1] for pt in bbox]
            xs = [pt[0] for pt in bbox]
            center_y = sum(ys) / len(ys)
            center_x = sum(xs) / len(xs)
            rows.append((center_y, center_x, str(text).strip()))

        if not rows:
            return ""

        # y 좌표 기준 정렬
        rows.sort(key=lambda r: r[0])

        # 같은 행으로 묶기 (y 차이가 이미지 높이의 2% 이내면 같은 행)
        max_y = max(r[0] for r in rows)
        min_y = min(r[0] for r in rows)
        y_range = max_y - min_y if max_y != min_y else 100
        row_threshold = y_range * 0.025  # 2.5% 범위

        grouped: list[list[tuple[float, float, str]]] = []
        current_group: list[tuple[float, float, str]] = [rows[0]]

        for row in rows[1:]:
            if abs(row[0] - current_group[-1][0]) <= row_threshold:
                current_group.append(row)
            else:
                grouped.append(current_group)
                current_group = [row]
        grouped.append(current_group)

        # 각 행 내부를 x 좌표 순으로 정렬 후 "라벨: 값" 형태로 조합
        lines: list[str] = []
        for group in grouped:
            group.sort(key=lambda r: r[1])  # x 오름차순
            texts = [r[2] for r in group if r[2]]
            if not texts:
                continue
            if len(texts) == 1:
                lines.append(texts[0])
            elif len(texts) == 2:
                lines.append(f"{texts[0]}: {texts[1]}")
            else:
                # 3개 이상이면 첫 번째가 라벨, 나머지가 값
                label = texts[0]
                value = " ".join(texts[1:])
                lines.append(f"{label}: {value}")

        return "\n".join(lines)

    def _clean_with_llm(self, raw_text: str) -> str:
        """LLM으로 노이즈를 제거하고 산업 속성 텍스트만 남긴다."""
        # 텍스트가 너무 짧으면 정제 불필요
        if len(raw_text.strip()) < 10:
            return raw_text
        if len(raw_text) > self.max_llm_cleaning_chars:
            return raw_text

        prompt = build_text_cleaning_prompt(raw_text)
        try:
            cleaned = self.client.generate(prompt)
            return cleaned.strip() if cleaned else raw_text
        except Exception as e:
            if self.fail_fast:
                raise
            print(f"[DocumentProcessor] LLM 정제 실패, 원본 텍스트 사용: {e}")
            return raw_text
