import json

# 사전 파일 로드
path = 'repositories/eclass_dictionary/eclass_properties.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 실제 딕셔너리 데이터만 추출
items = [e for e in data if isinstance(e, dict)]

# 테스트할 키워드들 (이미지에서 읽어올 법한 단어들)
test_keywords = ['Rated voltage', 'Degree of protection', 'Mass', 'Manufacturer name']

print('='*50)
print(' [실전 매핑 테스트 결과] ')
print('='*50)

for k in test_keywords:
    # 키워드가 포함된 가장 적절한 IRDI 찾기
    irdi = next((e.get('irdi') for e in items if k.lower() in e.get('preferred_name', '').lower()), "매칭 실패")
    print(f'검색어: {k}')
    print(f' -> 찾은 IRDI: {irdi}\n')

print('='*50)
print(f'테스트 완료: 총 {len(items)}개 데이터 중 검색 수행')