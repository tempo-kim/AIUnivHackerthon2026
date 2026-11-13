"""학교 생활 Q&A 챗봇.

매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 사용.
시연용 '긴 채팅' 200개(각 >=30메시지)에서 질문과 관련 대화를 골라 근거로 답한다.
"""

from __future__ import annotations

import json
import os
import traceback
from functools import lru_cache
from pathlib import Path

from ai.extractor import _client, _model_name

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "school_bot_seed_chats.json"


def _role_label(role: str) -> str:
    value = (role or "").strip().lower()
    if value in ("senior", "mentor"):
        return "선배"
    if value in ("junior",):
        return "후배"
    return "사용자"


@lru_cache(maxsize=1)
def load_seed_conversations() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    try:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[school_bot] seed load failed: {e}")
        return []

    # schema v2: conversations[]
    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        out: list[dict] = []
        for raw in data["conversations"]:
            if not isinstance(raw, dict):
                continue
            messages = raw.get("messages") or []
            cleaned = []
            for m in messages:
                if not isinstance(m, dict):
                    continue
                text = str(m.get("text") or "").strip()
                if not text:
                    continue
                cleaned.append(
                    {
                        "senderRole": str(m.get("senderRole") or "junior"),
                        "text": text,
                    }
                )
            if cleaned:
                out.append(
                    {
                        "id": str(raw.get("id") or ""),
                        "topic": str(raw.get("topic") or ""),
                        "title": str(raw.get("title") or ""),
                        "messages": cleaned,
                    }
                )
        return out

    # schema v1 fallback: flat messages
    rows = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    by_room: dict[str, list[dict]] = {}
    topic_by_room: dict[str, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        room = str(item.get("room") or "seed")
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        by_room.setdefault(room, []).append(
            {
                "senderRole": str(item.get("senderRole") or "junior"),
                "text": text,
            }
        )
        if item.get("topic"):
            topic_by_room[room] = str(item.get("topic"))
    return [
        {
            "id": room,
            "topic": topic_by_room.get(room, ""),
            "title": room,
            "messages": msgs,
        }
        for room, msgs in by_room.items()
    ]


def seed_stats() -> dict:
    convs = load_seed_conversations()
    return {
        "conversation_count": len(convs),
        "message_count": sum(len(c["messages"]) for c in convs),
    }


def _score_conversation(question: str, school: str, conv: dict) -> int:
    q = f"{school} {question}".lower()
    blob = f"{conv.get('topic','')} {conv.get('title','')} " + " ".join(
        m["text"] for m in conv.get("messages", [])[:8]
    )
    blob = blob.lower()
    score = 0
    for token in [
        "맛집",
        "밥",
        "카페",
        "샤로",
        "녹두",
        "낙성",
        "김밥",
        "치킨",
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
    # light token overlap
    for word in [w for w in q.replace("?", " ").split() if len(w) >= 2][:12]:
        if word in blob:
            score += 1
    if "맛집" in (conv.get("topic") or "") and any(k in q for k in ("밥", "맛집", "카페", "먹")):
        score += 5
    if "인공" in (conv.get("topic") or "") and any(
        k in q for k in ("인공", "전공", "과제", "머신", "모델", "연구")
    ):
        score += 5
    return score


def retrieve_conversations(
    question: str,
    *,
    school: str = "",
    top_k: int = 2,
) -> list[dict]:
    convs = load_seed_conversations()
    ranked = sorted(
        convs,
        key=lambda c: _score_conversation(question, school, c),
        reverse=True,
    )
    return ranked[: max(1, top_k)]


def format_conversations(convs: list[dict], *, max_chars: int = 14000) -> str:
    chunks: list[str] = []
    for conv in convs:
        lines = [
            f"### 채팅 {conv.get('id')} | {conv.get('topic')} | {conv.get('title')}",
        ]
        for m in conv.get("messages", []):
            lines.append(f"[{_role_label(m.get('senderRole',''))}] {m.get('text','')}")
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
    stats = seed_stats()
    if not question:
        return {
            "answer": "질문을 입력해 주세요.",
            "used_message_count": 0,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": 0,
            "seed_conversation_count": stats["conversation_count"],
            "source": "empty",
        }

    picked = retrieve_conversations(question, school=school, top_k=2)
    # optional: append a few live messages as extra context notes
    live = messages or []
    live_note = ""
    if live:
        live_lines = []
        for item in live[-20:]:
            text = str(item.get("text") or "").strip()
            if text:
                live_lines.append(
                    f"- [{_role_label(str(item.get('senderRole') or ''))}] {text[:300]}"
                )
        if live_lines:
            live_note = "\n\n[최근 실제 서비스 채팅 일부]\n" + "\n".join(live_lines)

    context = format_conversations(picked) + live_note
    used_msgs = sum(len(c.get("messages") or []) for c in picked)

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {
            "answer": (
                "아직 API 키가 없어 임시 안내만 할 수 있어요. "
                "backend/.env 에 매칭과 같은 OPENAI_API_KEY 를 넣으면, "
                f"시연용 긴 채팅 {stats['conversation_count']}개"
                f"(총 {stats['message_count']}메시지) 중 관련 대화를 골라 답합니다."
            ),
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
            "source": "no_key",
        }

    school_line = (
        f"대상 학교: {school}"
        if school.strip()
        else "대상 학교: (미지정, 시연 데이터는 서울대 캠퍼스/인공지능학과 기준)"
    )

    system_prompt = f"""
너는 대학 캠퍼스 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
아래에는 선배와 후배가 한 주제 안에서 길게 나눈 채팅 전문이 있다.
반드시 이 채팅에 나온 구체적 정보(가게·가격·웨이팅·과제 팁·절차)를 근거로 답한다.
일반 상식으로 대충 답하지 말고, 근거가 없으면 모른다고 말해라.

규칙:
- 한국어로 친절하고 구체적으로.
- 가능하면 참고 채팅의 디테일을 인용하듯 활용.
- 개인정보 추론/실존 인물 비방 금지.
- {school_line}
"""

    user_prompt = f"""
[참고용 선후배 긴 채팅]
{context}

[사용자 질문]
{question}
"""

    try:
        res = _client().chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            temperature=0.2,
            max_tokens=900,
            timeout=35.0,
        )
        answer = (res.choices[0].message.content or "").strip()
        if not answer:
            answer = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
        return {
            "answer": answer,
            "used_message_count": used_msgs,
            "seed_message_count": stats["message_count"],
            "used_conversation_count": len(picked),
            "seed_conversation_count": stats["conversation_count"],
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
            "source": "error",
        }
