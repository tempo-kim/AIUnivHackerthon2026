"""키 없이 쓸 수 있는 임시 추출기.

실제 LLM 추출은 AI/extraction 브랜치의 extractor.py 를 사용한다.
키가 없거나 LLM 호출이 실패하면 이 stub 으로 데모를 이어간다.
"""

from __future__ import annotations

KEYWORD_MAP: dict[str, list[str]] = {
    "수강신청": ["수강신청"],
    "시간표": ["시간표"],
    "수강계획": ["수강계획"],
    "통학": ["장거리 통학"],
    "기숙사": ["기숙사 생활"],
    "편입": ["편입"],
    "학점": ["학점 인정"],
    "복수전공": ["복수전공"],
    "경영": ["경영학과"],
    "컴공": ["컴퓨터공학과"],
    "컴퓨터": ["컴퓨터공학과"],
}


def stub_extract(concern_text: str) -> dict:
    text = concern_text or ""
    help_fields: list[str] = []
    interests: list[str] = []

    for needle, mapped in KEYWORD_MAP.items():
        if needle in text:
            for item in mapped:
                if item.endswith("학과"):
                    interests.append(item)
                else:
                    help_fields.append(item)

    # 중복 제거, 순서 유지
    def unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    help_fields = unique(help_fields)
    interests = unique(interests)

    if not help_fields and not interests:
        help_fields = ["수강신청"]

    return {
        "interests": interests,
        "situation": text.strip()[:120],
        "help_fields": help_fields,
    }
