"""API 키 없을 때 쓰는 키워드 기반 임시 추출."""

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
    "화학공학": ["화학공학과"],
    "화공": ["화학공학과"],
    "디자인": ["디자인과"],
    "시각디자인": ["시각디자인학과"],
    "심리": ["심리학과"],
    "간호": ["간호학과"],
    "식품영양": ["식품영양학과"],
    "식품공학": ["식품공학과"],
    "관광": ["관광경영학과"],
    "컴공": ["컴퓨터공학과"],
    "컴퓨터": ["컴퓨터공학과"],
    "진로": ["진로 탐색"],
    "취업": ["취업 준비"],
    "인턴": ["인턴십"],
    "대외": ["대외활동"],
    "동아리": ["동아리와 모임"],
    "친구": ["친구 사귀기"],
    "학교생활": ["학교생활"],
    "학교적응": ["학교생활"],
    "전공과목": ["수강신청"],
    "밥집": ["학교생활"],
    "대학원": ["대학원연구"],
    "연구실": ["대학원연구"],
    "랩실": ["대학원연구"],
    "논문": ["대학원연구"],
    "프로젝트": ["인턴대외활동"],
    "공모전": ["인턴대외활동"],
    "자격증": ["진로취업"],
    "면접": ["진로취업"],
    "전공": ["전공공부"],
    "공부": ["전공공부"],
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
        help_fields = ["학교생활"]

    return {
        "interests": interests,
        "situation": text.strip()[:160],
        "help_fields": help_fields,
    }
