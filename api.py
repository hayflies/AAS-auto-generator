"""FastAPI 백엔드 — 파일 업로드 → 파이프라인 → DB → AAS JSON 반환."""

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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import PipelineConfig
from app.pipeline import create_llm_pipeline
from app.text import slugify
from db import delete_result, get_result, init_db, list_results, save_result

app = FastAPI(title="AAS Generator", version="1.0.0")

# DB 초기화
init_db()

# Static 파일 서빙 (index.html)
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate")
async def generate_aas(
    files: Annotated[list[UploadFile], File(description="이미지 또는 PDF 파일")],
    name: Annotated[str, Form()] = "",
    manufacturer: Annotated[str, Form()] = "",
    asset_type: Annotated[str, Form()] = "",
):
    """업로드된 파일로 AAS를 생성하고 DB에 저장한다."""
    if not files:
        raise HTTPException(status_code=400, detail="파일을 1개 이상 업로드하세요.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_paths: list[str] = []
        for upload in files:
            dest = Path(tmp_dir) / (upload.filename or "upload")
            with open(dest, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            saved_paths.append(str(dest))

        asset_name = name or Path(saved_paths[0]).stem.replace("_", " ").title()
        asset_id = slugify(asset_name)

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

    prop_count = sum(
        len(sm.get("submodelElements", []))
        for sm in result.aas_json.get("submodels", [])
    )

    db_id = save_result(
        asset_id=result.asset_package.asset_id,
        asset_name=asset_name,
        aas_json=result.aas_json,
        property_count=prop_count,
    )

    return {
        "id": db_id,
        "asset_id": result.asset_package.asset_id,
        "asset_name": asset_name,
        "property_count": prop_count,
        "is_valid": result.aas_validation.get("is_valid", False),
        "aas_json": result.aas_json,
    }


@app.get("/api/results")
async def api_list_results() -> list[dict]:
    """저장된 AAS 결과 목록을 반환한다."""
    return list_results()


@app.get("/api/results/{result_id}")
async def api_get_result(result_id: int) -> dict:
    """특정 AAS 결과를 반환한다."""
    result = get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return result


@app.delete("/api/results/{result_id}")
async def api_delete_result(result_id: int) -> dict:
    """특정 AAS 결과를 삭제한다."""
    if not delete_result(result_id):
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return {"message": "삭제 완료"}


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
