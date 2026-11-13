"""학교 생활 Q&A 챗봇.

매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 사용.
선택한 학교의 긴 채팅(각 ≥30메시지)을 조회해 근거로 답한다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

# 매칭과 동일한 OpenAI/OpenRouter 클라이언트·모델 (OPENAI_* / LLM_MODEL)
from ai.extractor import _client, _llm_executor, _model_name

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "school_bot_seed_chats.json"

SCHOOL_ALIASES = {
    "서울대": "서울대학교",
    "서울대학교": "서울대학교",
    "고려대": "고려대학교",
    "고려대학교": "고려대학교",
    "연세대": "연세대학교",
    "연세대학교": "연세대학교",
    "이화여대": "이화여자대학교",
    "이화여자대학교": "이화여자대학교",
    "서울과기대": "서울과학기술대학교",
    "서울과학기술대학교": "서울과학기술대학교",
    "서강대": "서강대학교",
    "서강대학교": "서강대학교",
}

FOOD_HINTS = (
    "밥",
    "밥집",
    "맛집",
    "식당",
    "혼밥",
    "점심",
    "저녁",
    "배달",
    "카페",
    "카공",
    "콘센트",
    "와이파이",
)

MAJOR_HINTS = (
    "전공",
    "과제",
    "머신러닝",
    "딥러닝",
    "학점",
    "수강",
    "팀플",
    "gpu",
    "논문",
)


def normalize_school(school: str) -> str:
    value = (school or "").strip()
    if not value:
        return ""
    if value in SCHOOL_ALIASES:
        return SCHOOL_ALIASES[value]
    for key, canon in SCHOOL_ALIASES.items():
        if key in value or value in key:
            return canon
    return value


def _role_label(role: str) -> str:
    value = (role or "").strip().lower()
    if value in ("senior", "mentor"):
        return "선배"
    if value in ("junior",):
        return "후배"
    return "사용자"


@lru_cache(maxsize=1)
def _raw_seed() -> dict:
    if not SEED_PATH.exists():
        return {}
    try:
        return json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[school_bot] seed load failed: {e}")
        return {}


def load_seed_conversations(school: str = "") -> list[dict]:
    data = _raw_seed()
    canon = normalize_school(school)

    # schema v3
    by_school = data.get("conversations_by_school") if isinstance(data, dict) else None
    if isinstance(by_school, dict):
        if canon and canon in by_school:
            return list(by_school.get(canon) or [])
        # school unknown: flatten all
        out: list[dict] = []
        for rows in by_school.values():
            if isinstance(rows, list):
                out.extend(rows)
        return out

    # schema v2
    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        rows = data["conversations"]
        if canon:
            return [c for c in rows if normalize_school(str(c.get("school") or "")) == canon]
        return list(rows)

    return []


def seed_stats(school: str = "") -> dict:
    convs = load_seed_conversations(school)
    return {
        "conversation_count": len(convs),
        "message_count": sum(len(c.get("messages") or []) for c in convs),
        "school": normalize_school(school) or "(all)",
    }


def _score_conversation(question: str, school: str, conv: dict) -> int:
    # 학교 이름은 모든 해당 학교 대화에 들어 있으므로 검색어로 점수화하지 않는다.
    q = (question or "").lower()
    for alias in sorted(SCHOOL_ALIASES, key=len, reverse=True):
        q = q.replace(alias.lower(), " ")
    canonical_school = normalize_school(school).lower()
    if canonical_school:
        q = q.replace(canonical_school, " ")
    stop_words = {
        "학교", "우리", "근처", "기준", "추천", "좀", "알려", "주세요", "해줘",
        "궁금", "찾아", "좋은", "어디", "뭐가", "있나요", "있어요", "하고",
        "싶어요", "싶어", "부탁", "가능", "관련", "대해", "수", "때", "팁", "꿀팁",
    }
    query_terms = {
        term for term in re.findall(r"[가-힣A-Za-z0-9]+", q)
        if len(term) >= 2
        and term not in stop_words
        and not re.fullmatch(r"\d+학년|\d+학기", term)
    }
    if "카공" in q or "공부하기 좋은" in q:
        query_terms.update(("카페", "콘센트", "와이파이", "공부"))
    msgs = conv.get("messages") or []
    topic_title = f"{conv.get('topic','')} {conv.get('title','')}".lower()
    blob = topic_title + " " + " ".join(
        str(m.get("text") or "") for m in msgs[:24]
    )
    blob = blob.lower()
    score = sum(5 if term in topic_title else 1 for term in query_terms if term in blob)
    if any(token in q for token in FOOD_HINTS) and any(
        token in topic_title for token in ("맛집", "식당", "캠퍼스_주변")
    ):
        score += 8
    if any(token in q for token in MAJOR_HINTS) and any(
        token in topic_title for token in ("인공지능", "전공", "학업")
    ):
        score += 5
    return score


def retrieve_conversations(question: str, *, school: str = "", top_k: int = 3) -> list[dict]:
    convs = load_seed_conversations(school)
    if not convs:
        convs = load_seed_conversations("")
    scored = [(_score_conversation(question, school, conv), conv) for conv in convs]
    ranked = [conv for score, conv in sorted(scored, key=lambda row: row[0], reverse=True) if score > 0]
    selected: list[dict] = []
    seen: set[str] = set()
    target = max(2, top_k)
    for conv in ranked:
        signature = "|".join(
            [
                str(conv.get("topic") or ""),
                str(conv.get("title") or ""),
                str(conv.get("id") or ""),
            ]
        )
        if signature in seen:
            continue
        seen.add(signature)
        selected.append(conv)
        if len(selected) >= target:
            break
    return selected


def _intent(question: str) -> str:
    q = (question or "").strip().lower()
    if any(token in q for token in FOOD_HINTS):
        return "food"
    if any(token in q for token in MAJOR_HINTS):
        return "major"
    return "general"


def _fallback_answer_from_seed(question: str, convs: list[dict], school: str) -> str:
    school_name = school or "해당 학교"
    if not convs:
        return (
            f"{school_name} 시드 대화에서 질문과 직접 관련된 내용을 찾지 못했어요. "
            "과목명이나 위치, 원하는 정보(가격·분위기·공부 팁 등)를 더 알려주시면 다시 찾아볼게요."
        )
    if len((question or "").strip()) <= 2:
        return (
            f"{school_name} 기준으로 도와줄 수 있어요. "
            "밥집/카페 추천, 수강/과제, 전공 고민 중 어떤 걸 물어볼지 한 문장으로 알려줘요."
        )

    intent = _intent(question)
    lines: list[str] = [f"{school_name} 기준으로 참고 가능한 선후배 대화 요약이에요."]
    shown = 0
    seen_points: set[str] = set()
    for conv in convs:
        title = str(conv.get("title") or "").strip()
        msgs = conv.get("messages") or []
        senior_msg = next(
            (
                str(m.get("text") or "").strip()
                for m in msgs
                if str(m.get("senderRole") or "").strip().lower() in ("senior", "mentor")
                and str(m.get("text") or "").strip()
            ),
            "",
        )
        if not senior_msg:
            continue
        point = senior_msg[:80]
        if point in seen_points:
            continue
        seen_points.add(point)
        if title:
            lines.append(f"- {title}: {senior_msg[:140]}")
        else:
            lines.append(f"- {senior_msg[:140]}")
        shown += 1
        if shown >= 3:
            break
    if shown == 0:
        return "관련 시드 대화를 찾지 못했어요. 예산·위치·시간대를 함께 알려주면 더 정확히 찾아볼게요."
    if intent == "food":
        lines.append("예산·위치·시간대를 알려주면 더 좁혀서 추천해줄게요.")
    elif intent == "major":
        lines.append("학년·현재 수강 과목·막힌 지점을 알려주면 주간 공부 루틴으로 구체화해줄게요.")
    else:
        lines.append("상황을 조금만 더 구체적으로 알려주면 근거 대화를 더 정확히 골라 답할게요.")
    return "\n".join(lines)


def format_conversations(convs: list[dict], *, max_chars: int = 14000) -> str:
    chunks: list[str] = []
    for conv in convs:
        lines = [
            f"### 채팅 {conv.get('id')} | {conv.get('school','')} | {conv.get('topic')} | {conv.get('title')}",
        ]
        for m in conv.get("messages") or []:
            lines.append(f"[{_role_label(str(m.get('senderRole') or ''))}] {m.get('text','')}")
        chunks.append("\n".join(lines))
    blob = "\n\n".join(chunks)
    if len(blob) > max_chars:
        blob = blob[:max_chars]
    return blob


def answer_school_question(
    question: str,
    *,
    school: str = "",
    messages: list[dict] | None = None,
) -> dict:
    question = (question or "").strip()
    canon = normalize_school(school)
    stats = seed_stats(canon)
    if not question:
        return {
            "answer": "질문을 입력해 주세요.",
            "used_message_count": 0,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": 0,
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": "empty",
        }

    picked = retrieve_conversations(question, school=canon, top_k=3)
    live = messages or []
    live_note = ""
    if live:
        lines = []
        for item in live[-20:]:
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(f"- [{_role_label(str(item.get('senderRole') or ''))}] {text[:300]}")
        if lines:
            live_note = "\n\n[최근 실제 서비스 채팅 일부]\n" + "\n".join(lines)

    context = format_conversations(picked) + live_note
    used_msgs = sum(len(c.get("messages") or []) for c in picked)

    # RAG는 학교 시드 채팅, 멘토 CSV, README를 검색한다. 검색 DB를 아직
    # 만들지 않았거나 임베딩 요청에 실패한 경우 기존 seed 문맥 LLM으로 이어간다.
    fallback_source = "seed-fallback:rag-unavailable"
    try:
        from ai.rag_service import VECTOR_DIR, answer_with_rag

        if not VECTOR_DIR.exists():
            fallback_source = "seed-fallback:index-missing"
        else:
            fallback_source = "seed-fallback:rag-error"
        rag_question = f"{canon}\n{question}" if canon else question
        rag = answer_with_rag(rag_question, k=5)
        answer = str(rag.get("answer") or "").strip()
        if answer:
            rag_contexts = rag.get("contexts") or []
            return {
                "answer": answer,
                "used_message_count": sum(
                    sum(1 for line in str(row.get("text") or "").splitlines()
                        if line.startswith("[후배]") or line.startswith("[선배]"))
                    for row in rag_contexts
                    if (row.get("metadata") or {}).get("doc_type") == "seed_chat"
                ),
                "seed_message_count": stats["message_count"],
                "used_conversation_count": len(rag_contexts),
                "seed_conversation_count": stats["conversation_count"],
                "school": canon or "",
                "source": "rag",
            }
    except Exception as exc:
        print(f"[school_bot] RAG unavailable; using seed context fallback ({type(exc).__name__})")

    school_line = f"대상 학교: {canon}" if canon else "대상 학교: (미지정)"
    system_prompt = f"""
너는 대학 캠퍼스 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
반드시 아래 [참고용 선후배 긴 채팅]에서 근거를 찾아 답한다.

규칙:
- 한국어로 답한다.
- {school_line} 맥락을 유지.
- 답변 형식:
  1) 핵심 답변 2~4문장
  2) 근거 bullet 2~4개 (채팅 내용 기반: 장소/가격/웨이팅/팁)
  3) 근거가 부족하면 모른다고 말하고 추가 질문 1개를 제시
- 참고 데이터에 없는 사실을 단정하지 않는다.
- 개인정보 추론 금지.
"""
    user_prompt = f"""
[참고용 선후배 긴 채팅]
{context}

[사용자 질문]
{question}
"""
    try:
        def _call():
            return _client().chat.completions.create(
                model=_model_name(),
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_prompt.strip()},
                ],
                temperature=0.1,
                max_tokens=650,
                timeout=28.0,
            )

        # 매칭과 같은 스레드풀 — 워커 4개라 매칭·학교봇 동시에도 한쪽만 굶지 않음
        future = _llm_executor.submit(_call)
        res = future.result(timeout=30.0)
        answer = (res.choices[0].message.content or "").strip()
        source = "llm-seed-context"
        if not answer:
            answer = _fallback_answer_from_seed(question, picked, canon)
            source = fallback_source
        return {
            "answer": answer,
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": source,
        }
    except Exception as e:
        # SDK 예외 문자열에는 요청 URL이나 민감한 설정값이 섞일 수 있어 기록하지 않는다.
        print(f"[school_bot] LLM request failed ({type(e).__name__})")
        return {
            "answer": _fallback_answer_from_seed(question, picked, canon),
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": fallback_source,
        }
