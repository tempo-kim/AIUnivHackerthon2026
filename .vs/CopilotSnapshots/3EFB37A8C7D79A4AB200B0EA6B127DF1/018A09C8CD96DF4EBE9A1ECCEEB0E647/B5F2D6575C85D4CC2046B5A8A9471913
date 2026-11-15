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
    target_majors = _target_majors(" ".join([situation, choice_reason, *interests]))
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
        mentor_categories = _categories(help_topics + experiences + [major, bio])
        major_norm = _normalize(major)
        target_hits = {
            target
            for target in target_majors
            if target == major_norm
            or target.replace("학과", "과") == major_norm
            or major_norm.replace("학과", "과") == target.replace("학과", "과")
            or target in major_norm
            or major_norm in target
        }
        if target_hits:
            score += 30.0
            reasons.append("줄글에서 요청한 전공 일치: " + ", ".join(sorted(target_hits)))

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
            score += 1.0
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
