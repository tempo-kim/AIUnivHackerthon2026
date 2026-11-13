"""학교 생활 Q&A 챗봇.

선배 매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 을 사용한다.
시연용 시드 채팅(서울대 맛집·인공지능학과) + 실제 저장된 채팅을 익명으로 묶어 맥락으로 넣는다.
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
def load_seed_messages() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    try:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[school_bot] seed load failed: {e}")
        return []
    rows = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "senderRole": str(item.get("senderRole") or "junior"),
                "text": text,
                "topic": str(item.get("topic") or ""),
            }
        )
    return out


def build_chat_context(messages: list[dict], *, max_chars: int = 12000) -> str:
    lines: list[str] = []
    for item in messages:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        topic = str(item.get("topic") or "").strip()
        prefix = f"({topic}) " if topic else ""
        lines.append(f"- {prefix}[{_role_label(str(item.get('senderRole') or ''))}] {text[:500]}")
    blob = "\n".join(lines)
    if len(blob) > max_chars:
        blob = blob[-max_chars:]
    return blob


def merge_corpus(live_messages: list[dict] | None, *, prefer_topics: list[str] | None = None) -> list[dict]:
    """시드 + 실제 채팅을 합친다. 시연에서는 시드가 핵심 지식 원천."""
    seed = list(load_seed_messages())
    live = list(live_messages or [])
    if prefer_topics:
        lowered = [t.lower() for t in prefer_topics if t]
        def score(item: dict) -> int:
            topic = str(item.get("topic") or "").lower()
            text = str(item.get("text") or "").lower()
            return sum(1 for t in lowered if t in topic or t in text)

        seed = sorted(seed, key=score, reverse=True)
    # 시드를 앞에 두고, 실제 대화는 뒤에 소량 첨부
    return seed + live


def _infer_topics(question: str, school: str) -> list[str]:
    q = f"{school} {question}".lower()
    topics: list[str] = []
    food_keys = ("맛집", "밥", "카페", "술", "샤로", "녹두", "낙성", "김밥", "치킨", "식당", "브런치", "해장")
    ai_keys = ("인공", "머신", "딥러닝", "모델", "과제", "연구", "논문", "gpu", "파이토치", "전공", "학점", "팀플")
    if any(k in q for k in food_keys):
        topics.append("맛집")
    if any(k in q for k in ai_keys):
        topics.append("인공")
    return topics


def answer_school_question(
    question: str,
    *,
    school: str = "",
    messages: list[dict] | None = None,
) -> dict:
    """같은 LLM 연결로 학교 관련 질문에 답한다."""
    question = (question or "").strip()
    if not question:
        return {
            "answer": "질문을 입력해 주세요.",
            "used_message_count": 0,
            "seed_message_count": 0,
            "source": "empty",
        }

    topics = _infer_topics(question, school)
    corpus_rows = merge_corpus(messages, prefer_topics=topics)
    # 프롬프트 길이 제한: 질문과 관련도 높은 앞에서부터 잘라 사용
    if len(corpus_rows) > 120:
        corpus_rows = corpus_rows[:120]
    context = build_chat_context(corpus_rows)
    seed_count = len(load_seed_messages())
    used = len(corpus_rows)

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {
            "answer": (
                "아직 API 키가 없어 임시 안내만 할 수 있어요. "
                "backend/.env 에 매칭과 같은 OPENAI_API_KEY 를 넣으면 "
                f"시연용 대화 {seed_count}개(+실제 채팅)를 바탕으로 답합니다."
            ),
            "used_message_count": used,
            "seed_message_count": seed_count,
            "source": "no_key",
        }

    school_line = f"대상 학교: {school}" if school.strip() else "대상 학교: (미지정, 시연 데이터는 서울대 캠퍼스 기준)"
    corpus = context if context else "(참고할 대화가 없습니다.)"

    system_prompt = f"""
너는 대학 캠퍼스 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
아래 참고 대화는 선배와 후배가 나눈 익명 대화(시연용 가상 데이터 포함)이다.
반드시 이 대화에 나온 구체적 정보(가게 이름, 가격대, 대기 시간, 과제 팁, 수강 팁 등)를 우선해 답한다.
일반 상식으로 대충 때우지 말고, 참고 대화에 없는 내용은 추측하지 말고 모른다고 말하거나 확인이 필요하다고 말해라.

규칙:
- 한국어로 친절하고 구체적으로 답한다.
- 참고 대화의 디테일(지명, 가격, 절차)을 인용하듯 활용한다.
- 특정 실존 인물 비방·개인정보 추론 금지.
- 의료·법률 확정 조언 금지.
- {school_line}
"""

    user_prompt = f"""
[참고용 익명 선후배 대화 모음]
{corpus}

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
            max_tokens=800,
            timeout=30.0,
        )
        answer = (res.choices[0].message.content or "").strip()
        if not answer:
            answer = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
        return {
            "answer": answer,
            "used_message_count": used,
            "seed_message_count": seed_count,
            "source": "llm",
        }
    except Exception as e:
        print(f"[school_bot] {e}")
        traceback.print_exc()
        return {
            "answer": "지금은 답변 서버에 연결하지 못했어요. API 키·네트워크를 확인해 주세요.",
            "used_message_count": used,
            "seed_message_count": seed_count,
            "source": "error",
        }
