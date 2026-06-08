from __future__ import annotations

from pathlib import Path
import trimesh

class ModelProcessor:
    """대용량 3D 모델(GLB/gltf)의 조립체 계층구조를 보존하면서 폴리곤 감축(Decimation)을 수행하는 처리 클래스."""

    def __init__(self, reduction_ratio: float = 0.3):
        """
        ModelProcessor 인스턴스를 초기화한다.

        Args:
            reduction_ratio (float): 원본 폴리곤 대비 보존할 비율 (기본값: 0.3, 즉 70% 감축)
        """
        self.reduction_ratio = reduction_ratio
        # 최적화를 진행할 최소 폴리곤 개수 (기준선)
        self.min_faces_to_optimize = 500

    def process(self, input_path: str, output_path: str | None = None) -> str:
        """입력된 3D 모델 파일을 최적화 가공하여 저장하고 최종 파일 경로를 반환한다.

        처리 공정:
        - force='scene' 옵션으로 파일 내 모든 개별 부품 노드(Scene Graph) 구조를 그대로 흡수한다.
        - 각 하위 부품(Geometry) 중 일정 개수 이상의 폴리곤을 가진 메쉬만 타겟팅하여 감축 연산을 수행한다.
        - 변형축(Node Matrix) 및 파츠별 고유 명칭은 원본 그대로 유지한 채 최종 최적화 파일을 내보낸다.
        """
        input_p = Path(input_path)
        if not input_p.exists():
            raise FileNotFoundError(f"3D 모델 파일을 찾을 수 없습니다: {input_path}")

        # 출력 경로가 정의되지 않은 경우 자동 명명 규칙 적용
        # 호출하는 곳에서 출력경로 명시 필요
        if output_path is None:
            final_output = input_p.parent / f"{input_p.stem}_optimized{input_p.suffix}"
        else:
            final_output = Path(output_path)

        try:
            # 단일 메쉬 병합을 방지하고 부품별 조립 관계를 Scene 객체 구조로 보존하여 로드
            scene = trimesh.load(str(input_p), force='scene')
            
            # Scene 구조 내에 분리되어 존재하는 개별 부품(Geometry) 데이터를 순회하며 가공 진행
            for name, geometry in scene.geometry.items():
                if isinstance(geometry, trimesh.Trimesh):
                    orig_faces = len(geometry.faces)
                    
                    # 1. 500개 미만의 작은 부품은 깎지 않고 패스 (버그 수정됨: < 기호 사용)
                    if orig_faces < self.min_faces_to_optimize:
                        continue
                    
                    # 2. 500개 이상인 거대 파츠들만 타겟 면 수 계산 후 압축 진행
                    target_faces = int(orig_faces * self.reduction_ratio)
                    
                    try:
                        # 노드 트리는 유지하고 메쉬 정점만 단순화
                        simplified_mesh = geometry.simplify_quadric_decimation(face_count = target_faces)
                        
                        # 가공된 메쉬를 다시 Scene의 geometry에 명확하게 교체 삽입
                        scene.geometry[name] = simplified_mesh
                        
                    except Exception as e:
                        # 특정 복잡한 파츠 단순화 예외 발생 시 원본 유지
                        print(f" [ModelProcessor] [{name}] 압축 실패! 원인: {e}")
                        continue
                        
            # 폴리곤 감축 처리가 완료된 Scene 데이터를 최종 포맷으로 내보내기
            scene.export(str(final_output), file_type='glb')
            
            return str(final_output)

        except Exception as e:
            raise RuntimeError(f"[ModelProcessor]3D 모델 최적화 공정 중 오류가 발생했습니다: {str(e)}")