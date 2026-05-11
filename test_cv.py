from pathlib import Path
import sys


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics가 설치되어 있지 않습니다. 설치 후 다시 실행하세요.")
        return

    model = YOLO('modules/cv/models/robot_parts_best.pt')
    image = input("테스트할 사진 경로 입력 (예: data/input/test.jpg): ").strip()

    if not Path(image).exists():
        print(f"파일 없음: {image}")
        sys.exit(1)

    results = model.predict(source=image, save=True, conf=0.25)
    print(f"\n결과 저장됨: {results[0].save_dir}")
    print("해당 폴더 열어서 확인해봐")


if __name__ == "__main__":
    main()
