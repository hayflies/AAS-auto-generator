"""FastAPI application for AAS generation and stored-result access."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import PipelineConfig
from app.db import delete_result, get_result, init_db, list_results, save_result
from app.pipeline import create_llm_pipeline
from app.text import slugify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"

app = FastAPI(title="AAS Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "https://aas-generator.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate")
async def generate_aas(
    documents: list[UploadFile] = File(default=[]),
    models: list[UploadFile] = File(default=[]),
    images: list[UploadFile] = File(default=[]),
    name: str = Form(""),
    manufacturer: str = Form(""),
    asset_type: str = Form(""),
) -> dict:
    """Generate and persist an AAS from uploaded source files."""

    uploads = documents + models + images
    if not uploads:
        raise HTTPException(status_code=400, detail="파일을 1개 이상 업로드하세요.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_paths: list[str] = []
        for upload in uploads:
            destination = Path(tmp_dir) / Path(upload.filename or "upload").name
            with destination.open("wb") as file:
                shutil.copyfileobj(upload.file, file)
            saved_paths.append(str(destination))

        asset_name = name or Path(saved_paths[0]).stem.replace("_", " ").title()
        payload = {
            "manual_files": saved_paths,
            "user_inputs": {
                "asset_id": slugify(asset_name),
                "asset_name": asset_name,
                "asset_type": asset_type or "unknown",
                **({"manufacturer": manufacturer} if manufacturer else {}),
            },
        }

        try:
            result = create_llm_pipeline(PipelineConfig()).run(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"파이프라인 오류: {exc}") from exc

    model_path = result.model_info.model_path
    if model_path and not Path(model_path).exists():
        model_path = None

    property_count = sum(
        len(submodel.get("submodelElements", []))
        for submodel in result.aas_json.get("submodels", [])
    )
    result_id = save_result(
        asset_id=result.asset_package.asset_id,
        asset_name=asset_name,
        aas_json=result.aas_json,
        property_count=property_count,
        model_path=model_path,
    )
    return {
        "id": result_id,
        "asset_id": result.asset_package.asset_id,
        "asset_name": asset_name,
        "property_count": property_count,
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
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=False)
