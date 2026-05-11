import json
import os
import argparse
from datetime import datetime
from datasets import load_dataset

# 설정
DEFAULT_JSON_PATH = "repositories/eclass_dictionary/eclass_properties.json"
DATASET_NAME = "JoBeer/eclassCorpus"
NAMEPLATE_METALABELS = ["NAMEPLATE", "MARKING", "IDENTIFICATION"]

def load_existing_dict(path):
    if not os.path.exists(path):
        return {}, "empty"
    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}, "corrupted"
    
    if isinstance(data, list):
        return {item['irdi']: item for item in data if 'irdi' in item}, "list_of_entries"
    elif isinstance(data, dict):
        first_val = next(iter(data.values()), None)
        if isinstance(first_val, dict) and 'irdi' in first_val:
            return data, "irdi_to_entry"
        return data, "alias_to_irdi"
    return {}, "unknown"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="미리보기 모드")
    args = parser.parse_args()

    print(f"HuggingFace 데이터셋 다운로드 중: {DATASET_NAME}...")
    ds = load_dataset(DATASET_NAME, split='train')
    print(f"-> {len(ds)}개 행 로드됨")

    existing_data, structure_type = load_existing_dict(DEFAULT_JSON_PATH)
    print(f"기존 사전: {len(existing_data)}개 엔트리 (구조: {structure_type})")

    final_dict = existing_data.copy()
    new_entries = 0
    merged_count = 0
    
    for row in ds:
        # 대소문자 무관하게 IRDI 찾기
        irdi = next((row[k] for k in row.keys() if k.lower() == 'irdi'), None)
        if not irdi: continue

        name = next((row[k] for k in row.keys() if k.lower() == 'name'), '')
        query = next((row[k] for k in row.keys() if k.lower() == 'query'), '')
        metalabel = str(next((row[k] for k in row.keys() if k.lower() == 'metalabel'), '')).upper()
        
        submodel = "Nameplate" if any(m in metalabel for m in NAMEPLATE_METALABELS) else "TechnicalData"

        entry = {
            "irdi": irdi,
            "preferred_name": name,
            "definition": query,
            "datatype": next((row[k] for k in row.keys() if k.lower() == 'datatype'), None),
            "unit": next((row[k] for k in row.keys() if k.lower() == 'unit'), None),
            "submodel_hint": submodel,
            "source": "eclassCorpus"
        }

        if irdi in final_dict:
            merged_count += 1
        else:
            final_dict[irdi] = entry
            new_entries += 1

    print("\n=== 머지 결과 ===")
    print(f"  신규 추가:              {new_entries}")
    print(f"  기존 IRDI 중복:         {merged_count}")
    print(f"  최종 사전 크기:          {len(final_dict)}개")

    if args.dry_run:
        print("\n[DRY-RUN] 실제 파일 쓰기는 건너뜁니다.")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{DEFAULT_JSON_PATH}.bak.{timestamp}.json"
        
        if os.path.exists(DEFAULT_JSON_PATH):
            os.rename(DEFAULT_JSON_PATH, backup_path)
            print(f"백업 생성: {backup_path}")
        
        with open(DEFAULT_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(list(final_dict.values()), f, indent=2, ensure_ascii=False)
        print(f"파일 저장 완료: {DEFAULT_JSON_PATH}")

if __name__ == "__main__":
    main()