"""학교 생활 Q&A 챗봇.

매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 사용.
선택한 학교의 긴 채팅(각 ≥30메시지)을 조회해 근거로 답한다.
"""

from __future__ import annotations

import json
import os
import traceback
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
    q = f"{school} {question}".lower()
    msgs = conv.get("messages") or []
    blob = f"{conv.get('topic','')} {conv.get('title','')} " + " ".join(
        str(m.get("text") or "") for m in msgs[:10]
    )
    blob = blob.lower()
    score = 0
    for token in [
        "맛집",
        "밥",
        "카페",
        "김밥",
        "치킨",
        "파스타",
        "인공",
        "머신",
        "딥러닝",
        "과제",
        "연구",
        "논문",
        "gpu",
        "전공",
        "학점",
        "팀플",
        "수강",
    ]:
        if token in q and token in blob:
            score += 3
    for word in [w for w in q.replace("?", " ").split() if len(w) >= 2][:12]:
        if word in blob:
            score += 1
    topic = str(conv.get("topic") or "")
    if "맛집" in topic and any(k in q for k in ("밥", "맛집", "카페", "먹", "식당")):
        score += 6
    if "인공" in topic or "전공" in topic:
        if any(k in q for k in ("인공", "전공", "과제", "머신", "모델", "연구", "학점")):
            score += 6
    return score


def retrieve_conversations(question: str, *, school: str = "", top_k: int = 2) -> list[dict]:
    convs = load_seed_conversations(school)
    if not convs:
        convs = load_seed_conversations("")
    ranked = sorted(convs, key=lambda c: _score_conversation(question, school, c), reverse=True)
    return ranked[: max(1, top_k)]


def format_conversations(convs: list[dict], *, max_chars: int = 14000) -> str:
    chunks: list[str] = []
    for conv in convs:
        lines = [
            f"### 채팅 {conv.get('id')} | {conv.get('school','')} | {conv.get('topic')} | {conv.get('title')}",
        ]
        if conv.get("fact_note"):
            lines.append(f"(사실메모) {conv.get('fact_note')}")
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

    picked = retrieve_conversations(question, school=canon, top_k=2)
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

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {
            "answer": (
                "아직 API 키가 없어 임시 안내만 할 수 있어요. "
                "backend/.env 에 매칭과 같은 OPENAI_API_KEY 를 넣으면, "
                f"{canon or '선택 학교'} 시연 채팅 {stats['conversation_count']}개"
                f"(메시지 {stats['message_count']}개)를 조회해 답합니다."
            ),
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": "no_key",
        }

    school_line = f"대상 학교: {canon}" if canon else "대상 학교: (미지정)"
    system_prompt = f"""
너는 대학 캠퍼스 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
아래는 해당 학교 선배·후배가 한 주제 안에서 길게 나눈 채팅이다.
반드시 이 채팅의 구체 정보(장소·가격·웨이팅·과제 팁)를 근거로 답하고,
일반 상식으로 대충 답하지 마라. 근거가 없으면 모른다고 말해라.

규칙:
- 한국어로 친절하고 구체적으로.
- {school_line} 맥락을 유지.
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
                temperature=0.2,
                max_tokens=900,
                timeout=40.0,
            )

        # 매칭과 같은 스레드풀 — 워커 4개라 매칭·학교봇 동시에도 한쪽만 굶지 않음
        future = _llm_executor.submit(_call)
        res = future.result(timeout=42.0)
        answer = (res.choices[0].message.content or "").strip() or "답변을 만들지 못했어요."
        return {
            "answer": answer,
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": "llm",
        }
    except Exception as e:
        print(f"[school_bot] {e}")
        traceback.print_exc()
        return {
            "answer": "지금은 답변 서버에 연결하지 못했어요. API 키·네트워크를 확인해 주세요.",
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "school": canon or "",
            "source": "error",
        }
