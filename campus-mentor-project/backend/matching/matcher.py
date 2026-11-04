"""규칙 기반 선배 매칭.

AI가 뽑은 interests / help_fields / situation 과
CSV 선배 프로필(major, experiences, help_topics)을 비교한다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mentor:
    mentor_id: str
    major: str
    experiences: list[str]
    help_topics: list[str]


def _split_pipe(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def load_mentors(csv_path: Path | None = None) -> list[Mentor]:
    if csv_path is None:
        csv_path = (
            Path(__file__).resolve().parents[2] / "data" / "mentors.example.csv"
        )
    mentors: list[Mentor] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mentors.append(
                Mentor(
                    mentor_id=row["mentor_id"].strip(),
                    major=row["major"].strip(),
                    experiences=_split_pipe(row.get("experiences", "")),
                    help_topics=_split_pipe(row.get("help_topics", "")),
                )
            )
    return mentors


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "")


def _tokens(values: list[str]) -> set[str]:
    return {_normalize(v) for v in values if v and v.strip()}


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
    mentors: list[Mentor] | None = None,
    top_k: int = 3,
) -> list[dict]:
    if mentors is None:
        mentors = load_mentors()

    query_help = _tokens(help_fields + interests)
    situation_norm = _normalize(situation)

    ranked: list[dict] = []
    for mentor in mentors:
        reasons: list[str] = []
        score = 0.0

        topic_hits = _overlap(query_help, _tokens(mentor.help_topics))
        if topic_hits:
            score += 3.0 * len(topic_hits)
            reasons.append(
                "도움 분야 일치: " + ", ".join(sorted(topic_hits))
            )

        exp_hits = _overlap(query_help, _tokens(mentor.experiences))
        if exp_hits:
            score += 2.0 * len(exp_hits)
            reasons.append(
                "경험 관련: " + ", ".join(sorted(exp_hits))
            )

        major_norm = _normalize(mentor.major)
        if major_norm and (
            major_norm in query_help
            or any(major_norm in t or t in major_norm for t in query_help)
            or (situation_norm and major_norm in situation_norm)
        ):
            score += 1.5
            reasons.append(f"전공 관련: {mentor.major}")

        if situation_norm:
            for exp in mentor.experiences:
                exp_norm = _normalize(exp)
                if exp_norm and (
                    exp_norm in situation_norm or situation_norm in exp_norm
                ):
                    score += 1.0
                    reasons.append(f"상황과 경험 유사: {exp}")
                    break

        if score <= 0:
            continue

        ranked.append(
            {
                "mentor_id": mentor.mentor_id,
                "major": mentor.major,
                "experiences": mentor.experiences,
                "help_topics": mentor.help_topics,
                "score": round(score, 2),
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]
