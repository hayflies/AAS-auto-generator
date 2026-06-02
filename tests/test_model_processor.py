import os
import trimesh
from modules.input_layer.model_processor import ModelProcessor

def verify_optimized_model(input_file: str):
    print("=" * 60)
    print(f"📦 1. 원본 3D 모델 분석 시작: {input_file}")
    print("=" * 60)
    
    # 1. 원본 데이터 상태 출력
    orig_scene = trimesh.load(input_file, force='scene')
    print(f"[원본] 하위 부품(Geometry) 개수: {len(orig_scene.geometry)}")
    for name, geo in orig_scene.geometry.items():
        if isinstance(geo, trimesh.Trimesh):
            print(f"  - 부품명: '{name}' | 폴리곤(Faces) 개수: {len(geo.faces)}")

    # 2. ModelProcessor 구동 (보존율 30% 설정)
    print("\n" + "=" * 60)
    print("⚙️ 2. Trimesh 데시메이션 공정 가동 (압축률 70%)")
    print("=" * 60)
    processor = ModelProcessor(reduction_ratio=0.3)
    output_file = processor.process(input_file)
    print(f"✨ 최적화 완료! 결과물 저장 경로: {output_file}")

    # 3. 최적화된 결과물 데이터 상태 출력 (무결성 검증)
    print("\n" + "=" * 60)
    print("🔍 3. 가공 결과물 구조 및 스펙 검증")
    print("=" * 60)
    opt_scene = trimesh.load(output_file, force='scene')
    print(f"[결과] 하위 부품(Geometry) 개수: {len(opt_scene.geometry)}")
    
    # 두 장면의 부품 개수 및 계층 정보가 똑같은지 체크
    if len(orig_scene.geometry) == len(opt_scene.geometry):
        print("✅ 성공: 부품 계층 구조(노드 트리) 개수가 원본과 100% 일치합니다.")
    else:
        print("❌ 경고: 부품 구조가 병합되었거나 유실되었습니다.")

    print("\n[부품별 면 수 가감 결과비교]")
    for name, opt_geo in opt_scene.geometry.items():
        if isinstance(opt_geo, trimesh.Trimesh):
            orig_geo = orig_scene.geometry.get(name)
            orig_faces = len(orig_geo.faces) if orig_geo else 0
            opt_faces = len(opt_geo.faces)
            
            # 감축 여부 판단 확인
            status = "📉 감축성공" if opt_faces < orig_faces else "🔒 원본보존 (500개 미만 파츠)"
            print(f"  - 부품명: '{name}'")
            print(f"    * 원본 면 수: {orig_faces}개 -> 가공 후 면 수: {opt_faces}개 [{status}]")

    # 파일 용량 비교 추가
    orig_size = os.path.getsize(input_file) / (1024 * 1024)
    opt_size = os.path.getsize(output_file) / (1024 * 1024)
    print("\n" + "=" * 60)
    print(f"📊 최종 용량 다이어트 리포트")
    print(f"   원본 파일 용량: {orig_size:.2f} MB")
    print(f"   최적화 파일 용량: {opt_size:.2f} MB (약 {((orig_size-opt_size)/orig_size)*100:.1f}% 감소)")
    print("=" * 60)

if __name__ == "__main__":
    # ⚠️ 테스트하고 싶은 원본 대용량 캐드(GLB) 파일 경로를 여기에 적어주세요.
    TEST_FILE_PATH = "data\\input\\Untitled.glb" 
    
    if TEST_FILE_PATH == "your_large_model.glb" or not os.path.exists(TEST_FILE_PATH):
        print("⚠️ 테스트를 진행하려면 TEST_FILE_PATH 변수에 실제 존재하는 .glb 파일 경로를 입력해야 합니다.")
    else:
        verify_optimized_model(TEST_FILE_PATH)