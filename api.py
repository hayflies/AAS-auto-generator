"""FastAPI 백엔드 — 파일 업로드 → 파이프라인 → DB → AAS JSON / GLB 반환."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware  # CORS 미들웨어 임포트

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import PipelineConfig
from app.pipeline import create_llm_pipeline
from app.text import slugify
from db import delete_result, get_result, init_db, list_results, save_result

app = FastAPI(title="AAS Generator", version="1.0.0")

# CORS 보안 정책 허용 설정
origins = [
    "http://localhost:3000",      # 로컬 React 기본 포트
    "http://localhost:5173",      # 로컬 Vite/React 기본 포트
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://aas-generator.vercel.app",  # 배포된 프론트엔드 주소
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 프론트엔드의 어떤 포트(3000, 5173 등)든 모두 허용
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, DELETE 등 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 HTTP 헤더 허용
)

init_db()

STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate")
async def generate_aas(
    # 프론트엔드 구조(UploadPage.tsx)에 맞춰서 파일들을 분리하여 수신 (비어있을 수 있으므로 기본값 설정)
    documents: list[UploadFile] = File(default=[]),
    models: list[UploadFile] = File(default=[]),
    images: list[UploadFile] = File(default=[]),
    # 텍스트 입력 데이터들도 개별 Form 데이터로 정확한 매칭 수신
    name: str = Form(""),
    manufacturer: str = Form(""),
    asset_type: str = Form(""),
):
    """업로드된 파일로 AAS를 생성하고 DB에 저장한다."""
    
    # 1. 프론트엔드가 따로 보낸 모든 파일들을 하나의 리스트로 통합
    all_files = documents + models + images

    if not all_files:
        raise HTTPException(status_code=400, detail="파일을 1개 이상 업로드하세요.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_paths: list[str] = []
        for upload in all_files:
            dest = Path(tmp_dir) / (upload.filename or "upload")
            with open(dest, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            saved_paths.append(str(dest))

        asset_name = name or Path(saved_paths[0]).stem.replace("_", " ").title()
        asset_id = slugify(asset_name)

        # 2. 내부 파이프라인 엔진이 기대하는 데이터 구조(Payload)를 그대로 조립
        payload = {
            "manual_files": saved_paths,
            "user_inputs": {
                "asset_id": asset_id,
                "asset_name": asset_name,
                "asset_type": asset_type or "unknown",
                **({"manufacturer": manufacturer} if manufacturer else {}),
            },
        }

        try:
            config = PipelineConfig()
            pipeline = create_llm_pipeline(config)
            result = pipeline.run(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"파이프라인 오류: {exc}") from exc

    # 파이프라인이 생성한 GLB 경로 (파일이 실제 존재할 때만 저장)
    model_path = result.model_info.model_path
    if model_path and not Path(model_path).exists():
        model_path = None

    prop_count = sum(
        len(sm.get("submodelElements", []))
        for sm in result.aas_json.get("submodels", [])
    )

    db_id = save_result(
        asset_id=result.asset_package.asset_id,
        asset_name=asset_name,
        aas_json=result.aas_json,
        property_count=prop_count,
        model_path=model_path,
    )

    return {
        "id": db_id,
        "asset_id": result.asset_package.asset_id,
        "asset_name": asset_name,
        "property_count": prop_count,
        "is_valid": result.aas_validation.get("is_valid", False),
        "aas_json": result.aas_json,
        "has_model": model_path is not None,
    }


@app.get("/api/results")
async def api_list_results() -> list[dict]:
    return list_results()


@app.get("/api/results/{result_id}")
async def api_get_result(result_id: int) -> dict:
    result = get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return result


@app.delete("/api/results/{result_id}")
async def api_delete_result(result_id: int) -> dict:
    if not delete_result(result_id):
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return {"message": "삭제 완료"}


@app.get("/api/models/{result_id}")
async def api_get_model(result_id: int) -> FileResponse:
    """파이프라인이 생성한 경량화 GLB 파일을 반환한다."""
    result = get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")

    model_path = result.get("model_path")
    if not model_path or not Path(model_path).exists():
        raise HTTPException(status_code=404, detail="3D 모델 파일이 없습니다.")

    return FileResponse(
        path=model_path,
        media_type="model/gltf-binary",
        filename=Path(model_path).name,
    )


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)