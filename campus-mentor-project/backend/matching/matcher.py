"""규칙 기반 선배 점수 + (선택) LLM 최종 추천 이유 보강 전 단계."""

from __future__ import annotations


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


def match_mentors(
    *,
    interests: list[str],
    help_fields: list[str],
    situation: str = "",
    mentors: list[dict] | None = None,
    top_k: int = 3,
) -> list[dict]:
    if not mentors:
        return []

    query_help = _tokens(list(help_fields) + list(interests))
    situation_norm = _normalize(situation)
    ranked: list[dict] = []

    for mentor in mentors:
        reasons: list[str] = []
        score = 0.0
        help_topics = list(mentor.get("help_topics") or [])
        experiences = list(mentor.get("experiences") or [])
        major = str(mentor.get("major") or "")
        bio = str(mentor.get("bio") or "")

        topic_hits = _overlap(query_help, _tokens(help_topics))
        if topic_hits:
            score += 3.0 * len(topic_hits)
            reasons.append("도움 분야 일치: " + ", ".join(sorted(topic_hits)))

        exp_hits = _overlap(query_help, _tokens(experiences))
        if exp_hits:
            score += 2.0 * len(exp_hits)
            reasons.append("경험 관련: " + ", ".join(sorted(exp_hits)))

        major_norm = _normalize(major)
        if major_norm and (
            major_norm in query_help
            or any(major_norm in t or t in major_norm for t in query_help)
            or (situation_norm and major_norm in situation_norm)
        ):
            score += 1.5
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
            continue

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
