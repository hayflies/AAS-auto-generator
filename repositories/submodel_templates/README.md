# Submodel Templates Repository

이 디렉토리는 AAS Submodel 템플릿을 보관하는 로컬 저장소입니다.

## 구성

- `default_submodels.json`: 프로젝트 초기에 사용하던 간단한 기본 Submodel 목록입니다.
- `admin_shell_io_submodel_templates/`: `admin-shell-io/submodel-templates` GitHub 저장소의 `main` 브랜치 내용을 로컬에 내려받은 전체 스냅샷입니다.

## Upstream Source

- Source: https://github.com/admin-shell-io/submodel-templates/tree/main
- Local path: `repositories/submodel_templates/admin_shell_io_submodel_templates/`
- Fetched at: 2026-05-11
- Included contents: `published/`, `deprecated/`, upstream `README.md`, `LICENSE.txt`, helper materials, GitHub workflow files

업스트림 라이선스는 `admin_shell_io_submodel_templates/LICENSE.txt`에 포함되어 있습니다.

## 사용 기준

템플릿 매칭에는 우선 `admin_shell_io_submodel_templates/published/` 아래의 JSON 템플릿을 사용합니다.

예시:

- Technical Data 1.2:
  `admin_shell_io_submodel_templates/published/Technical_Data/1/2/IDTA_02003-1-2_Template_TechnicalData.json`
- Digital Nameplate:
  `admin_shell_io_submodel_templates/published/Digital nameplate/3/`
- Contact Information:
  `admin_shell_io_submodel_templates/published/Contact Information/1/`

현재 로컬 스냅샷 기준 `published/` 아래에는 JSON 템플릿 151개, AASX 파일 148개, PDF 문서 70개가 포함되어 있습니다.

## 관리 주의점

전체 upstream 저장소를 그대로 포함했기 때문에 로컬 크기는 약 130MB입니다. 코드에서 매칭 성능과 Git 저장소 크기를 줄여야 한다면 다음 단계에서 `published/**/*.json`만 indexing하거나 필요한 template family만 선별하는 방식으로 정리할 수 있습니다.
