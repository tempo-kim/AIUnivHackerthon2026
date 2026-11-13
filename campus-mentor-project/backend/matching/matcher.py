"""규칙 기반 선배 점수. LLM 한 번 호출 전에 후보를 좁히는 데 쓴다."""

from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "")


def _tokens(values: list[str]) -> set[str]:
    return {_normalize(v) for v in values if v and str(v).strip()}


def _overlap(a: set[str], b: set[str]) -> set[str]:
    hits: set[str] = set()
    for left in a:
        for right in b:
            if left == right or left in right or right in left:
                hits.add(right)
    return hits


def _target_majors(text: str) -> set[str]:
    normalized = _normalize(text)
    return {
        match.group(1)
        for match in re.finditer(r"([가-힣A-Za-z0-9]+(?:학과|전공))", normalized)
    }


TRANSFER_KEYWORDS = ("전과", "복수전공", "전공변경", "학과변경", "전공전환")
FOOD_QUERY_KEYWORDS = (
    "밥",
    "밥집",
    "맛집",
    "식당",
    "혼밥",
    "점심",
    "저녁",
    "배달",
    "카페",
)
FOOD_PROFILE_HINTS = (
    "밥",
    "맛집",
    "식당",
    "혼밥",
    "카페",
    "배달",
    "웨이팅",
    "가성비",
    "점심",
    "저녁",
)


def _major_like(value: str) -> str:
    return _normalize(value).replace("학과", "과")


def _major_matches(target: str, major: str) -> bool:
    target_like = _major_like(target)
    major_like = _major_like(major)
    if not target_like or not major_like:
        return False
    return (
        target_like == major_like
        or target_like in major_like
        or major_like in target_like
    )


def _extract_transfer_route(text: str) -> tuple[str, str]:
    normalized = _normalize(text)
    match = re.search(
        r"([가-힣a-z0-9]+(?:학과|전공))에서([가-힣a-z0-9]+(?:학과|전공))(?:로|으로)?(?:전과|전공변경|전공전환)",
        normalized,
    )
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _has_transfer_intent(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(keyword) in normalized for keyword in TRANSFER_KEYWORDS)


def _has_food_intent(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(keyword) in normalized for keyword in FOOD_QUERY_KEYWORDS)


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "학교생활": ("학교생활", "학교적응", "동아리", "친구", "밥집", "통학", "기숙사", "학생회"),
    "전공공부": ("전공", "전공지식", "공부", "수강", "시간표", "학점", "복수전공", "과목"),
    "진로취업": ("진로", "취업", "커리어", "면접", "자격증", "직무", "채용"),
    "인턴대외활동": ("인턴", "대외활동", "공모전", "포트폴리오", "프로젝트"),
    "대학원연구": ("대학원", "연구", "랩실", "연구실", "논문", "학부연구생"),
}

PREFERENCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "취업 경험": ("취업", "진로", "면접", "채용"),
    "인턴 경험": ("인턴",),
    "대외활동 경험": ("대외활동", "공모전", "동아리", "학생회"),
    "대학원·연구 경험": ("대학원", "연구", "연구실", "랩실", "논문", "학부연구생"),
    "학교생활 경험": ("학교생활", "학교적응", "동아리", "친구", "통학", "기숙사", "학생회"),
}


def _categories(values: list[str] | tuple[str, ...] | str) -> set[str]:
    items = [values] if isinstance(values, str) else list(values)
    text = " ".join(_normalize(str(value)) for value in items if value)
    return {
        category
        for category, keywords in CATEGORY_KEYWORDS.items()
        if any(_normalize(keyword) in text for keyword in keywords)
    }


def _status_group(status: str) -> str:
    normalized = _normalize(status)
    if "졸업" in normalized:
        return "graduate"
    if "신입" in normalized or "1학년" in normalized or "2학년" in normalized:
        return "early"
    if "재학" in normalized or "3학년" in normalized or "4학년" in normalized or "5학년" in normalized:
        return "student"
    return ""


def match_mentors(
    *,
    interests: list[str],
    help_fields: list[str],
    situation: str = "",
    choice_reason: str = "",
    experience_preferences: list[str] | None = None,
    choice_status: str = "",
    mentors: list[dict] | None = None,
    top_k: int = 3,
) -> list[dict]:
    if not mentors:
        return []

    query_help = _tokens(list(help_fields) + list(interests) + ([choice_reason] if choice_reason else []))
    query_categories = _categories(list(help_fields) + list(interests) + [choice_reason, situation])
    choice_categories = _categories(choice_reason)
    preferences = experience_preferences or []
    situation_norm = _normalize(situation)
    context_text = " ".join([situation, choice_reason, *interests])
    target_majors = _target_majors(context_text)
    source_major, destination_major = _extract_transfer_route(context_text)
    has_transfer_intent = _has_transfer_intent(context_text)
    has_food_intent = _has_food_intent(context_text)
    ranked: list[dict] = []

    for mentor in mentors:
        reasons: list[str] = []
        score = 0.0
        help_topics = list(mentor.get("help_topics") or [])
        experiences = list(mentor.get("experiences") or [])
        major = str(mentor.get("major") or "")
        bio = str(mentor.get("bio") or "")
        mentor_status = str(mentor.get("status") or "")
        mentor_text = " ".join([major, mentor_status, *help_topics, *experiences, bio])
        mentor_text_norm = _normalize(mentor_text)
        mentor_categories = _categories(help_topics + experiences + [major, bio])
        major_norm = _normalize(major)
        if has_transfer_intent and destination_major:
            if _major_matches(destination_major, major_norm):
                score += 42.0
                reasons.append("전과 목표 전공 일치")
            elif source_major and _major_matches(source_major, major_norm):
                score += 8.0
                reasons.append("전과 출발 전공 관련")
        else:
            target_hits = {
                target
                for target in target_majors
                if _major_matches(target, major_norm)
            }
            if target_hits:
                score += 30.0
                reasons.append("줄글에서 요청한 전공 일치: " + ", ".join(sorted(target_hits)))

        if has_transfer_intent:
            transfer_hits = [kw for kw in TRANSFER_KEYWORDS if _normalize(kw) in mentor_text_norm]
            if transfer_hits:
                score += 18.0
                reasons.append("전과/전공변경 경험 관련")
            if source_major and destination_major:
                if source_major in mentor_text_norm and destination_major in mentor_text_norm:
                    score += 12.0
                    reasons.append("출발·목표 전공 전환 경험 유사")

        if has_food_intent:
            food_hits = [
                keyword
                for keyword in FOOD_PROFILE_HINTS
                if _normalize(keyword) in mentor_text_norm
            ]
            if food_hits:
                score += 22.0
                reasons.append("밥집/맛집 생활 경험 일치")
            else:
                score -= 12.0
                reasons.append("밥집/맛집 관련 근거 부족")

        preference_hits: list[str] = []
        for preference in preferences:
            if preference == "비슷한 전공":
                if major_norm := _normalize(major):
                    if major_norm in query_help or any(
                        major_norm in token or token in major_norm for token in query_help
                    ):
                        preference_hits.append(preference)
            elif preference == "비슷한 학년":
                user_group = _status_group(choice_status)
                if user_group and user_group == _status_group(mentor_status):
                    preference_hits.append(preference)
            elif any(_normalize(keyword) in _normalize(mentor_text) for keyword in PREFERENCE_KEYWORDS.get(preference, ())):
                preference_hits.append(preference)

        if preference_hits:
            score += 3.0 * len(preference_hits)
            reasons.append("선배 경험 조건 일치: " + ", ".join(preference_hits))

        category_hits = query_categories & mentor_categories
        choice_category_hits = choice_categories & mentor_categories
        if choice_category_hits:
            score += 6.0 * len(choice_category_hits)
            reasons.append("선택 분야 일치: " + ", ".join(sorted(choice_category_hits)))
        elif category_hits:
            score += 2.5 * len(category_hits)
            reasons.append("고민 분야 관련: " + ", ".join(sorted(category_hits)))

        topic_hits = _overlap(query_help, _tokens(help_topics))
        if topic_hits:
            score += 2.0 * len(topic_hits)
            reasons.append("도움 분야 일치: " + ", ".join(sorted(topic_hits)))

        exp_hits = _overlap(query_help, _tokens(experiences))
        if exp_hits:
            score += 1.5 * len(exp_hits)
            reasons.append("경험 관련: " + ", ".join(sorted(exp_hits)))

        if major_norm and (
            major_norm in query_help
            or any(major_norm in t or t in major_norm for t in query_help)
            or (situation_norm and major_norm in situation_norm)
        ):
            score += 0.3 if has_food_intent else 1.0
            reasons.append(f"전공 관련: {major}")

        if situation_norm:
            for exp in experiences:
                exp_norm = _normalize(exp)
                if exp_norm and (exp_norm in situation_norm or situation_norm in exp_norm):
                    score += 1.0
                    reasons.append(f"상황과 경험 유사: {exp}")
                    break
            bio_norm = _normalize(bio)
            if bio_norm:
                for token in query_help:
                    if token and token in bio_norm:
                        score += 0.5
                        reasons.append("소개글 키워드 관련")
                        break

        if score <= 0:
            score = 0.01
            reasons.append("선택 조건을 기준으로 한 기본 추천")

        ranked.append(
            {
                "mentor_id": mentor.get("mentor_id"),
                "display_name": mentor.get("display_name") or mentor.get("mentor_id"),
                "major": major,
                "experiences": experiences,
                "help_topics": help_topics,
                "bio": bio,
                "score": round(score, 2),
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]
