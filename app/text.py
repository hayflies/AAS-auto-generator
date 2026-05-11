from __future__ import annotations

import re


# CamelCase, snake_case, kebab-case가 섞여 들어와도 검색/매칭에 쓸 수 있도록
# 모든 이름을 토큰 단위로 정규화한다.
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_label(value: str) -> str:
    """사람이 읽는 라벨 형태로 문자열을 정규화한다."""
    spaced = _CAMEL_BOUNDARY.sub(" ", value.replace("_", " ").replace("-", " "))
    return " ".join(spaced.split())


def tokenize(value: str | None) -> set[str]:
    """후보 검색과 rule-based matching에 사용할 소문자 토큰 집합을 만든다."""
    if not value:
        return set()
    return set(_TOKEN.findall(normalize_label(value).lower()))


def slugify(value: str, fallback: str = "asset") -> str:
    """자산 ID나 파일명에 안전하게 쓸 수 있는 slug를 만든다.

    전부 대문자인 단어(예: ROBOTIS)는 소문자로 바꾼 뒤 처리해서
    글자 하나씩 쪼개지는 문제를 방지한다.
    """
    tokens = _TOKEN.findall(value.lower().replace("_", " ").replace("-", " "))
    return "_".join(tokens) or fallback


def to_id_short(value: str, fallback: str = "GeneratedAsset") -> str:
    """AAS idShort에 어울리는 PascalCase 식별자를 만든다."""
    tokens = _TOKEN.findall(normalize_label(value).lower())
    if not tokens:
        return fallback
    head, *tail = tokens
    return head[:1].upper() + head[1:] + "".join(item[:1].upper() + item[1:] for item in tail)
