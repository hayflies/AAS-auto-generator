"""프로젝트 최상위 실행 파일.

팀원이 루트 디렉터리에서 `python3 main.py`로 바로 파이프라인을 실행할 수
있도록 실제 CLI 구현은 `app.main`에 위임한다.
"""

from app.main import main


if __name__ == "__main__":
    main()
