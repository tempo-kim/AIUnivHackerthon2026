"""학교 생활 Q&A 챗봇 — 사실 DB + 긴 채팅 하이브리드 검색.

매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 사용.
1) school_bot_facts.json 의 실존 교통·전공·맛집 카드
2) school_bot_seed_chats.json 의 학교별 긴 채팅
을 함께 조회해 근거로 답한다. 키 없으면 사실 카드로 추출 답변.
"""

from __future__ import annotations

import json
import os
import re
import atexit
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from ai.extractor import _client, _model_name

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SEED_PATH = DATA_DIR / "school_bot_seed_chats.json"
FACTS_PATH = DATA_DIR / "school_bot_facts.json"
_school_bot_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="school-bot-llm")
atexit.register(lambda: _school_bot_executor.shutdown(wait=False, cancel_futures=True))

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


def _tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[\s,?!.·~/()]+", (text or "").lower()) if len(w) >= 2]


@lru_cache(maxsize=1)
def _raw_seed() -> dict:
    if not SEED_PATH.exists():
        return {}
    try:
        return json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[school_bot] seed load failed: {e}")
        return {}


@lru_cache(maxsize=1)
def _raw_facts() -> dict:
    if not FACTS_PATH.exists():
        return {}
    try:
        return json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[school_bot] facts load failed: {e}")
        return {}


def load_seed_conversations(school: str = "") -> list[dict]:
    data = _raw_seed()
    canon = normalize_school(school)
    by_school = data.get("conversations_by_school") if isinstance(data, dict) else None
    if isinstance(by_school, dict):
        if canon and canon in by_school:
            return list(by_school.get(canon) or [])
        out: list[dict] = []
        for rows in by_school.values():
            if isinstance(rows, list):
                out.extend(rows)
        return out
    if isinstance(data, dict) and isinstance(data.get("conversations"), list):
        rows = data["conversations"]
        if canon:
            return [c for c in rows if normalize_school(str(c.get("school") or "")) == canon]
        return list(rows)
    return []


def school_fact_bundle(school: str) -> dict:
    canon = normalize_school(school)
    schools = (_raw_facts() or {}).get("schools") or {}
    if canon and canon in schools:
        return dict(schools[canon])
    return {}


def iter_fact_cards(school: str = "") -> list[dict]:
    """평탄화된 사실 카드 목록."""
    canon = normalize_school(school)
    schools = (_raw_facts() or {}).get("schools") or {}
    targets = {canon: schools[canon]} if canon and canon in schools else schools
    cards: list[dict] = []
    for school_name, bundle in targets.items():
        if not isinstance(bundle, dict):
            continue
        for section in ("transit", "campus_life"):
            for item in bundle.get(section) or []:
                if isinstance(item, dict):
                    cards.append({**item, "school": school_name, "section": section})
        ai = bundle.get("ai_program")
        if isinstance(ai, dict):
            cards.append({**ai, "school": school_name, "section": "ai_program"})
        for r in bundle.get("restaurants") or []:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "")
            cards.append(
                {
                    "id": f"food-{school_name}-{name}",
                    "school": school_name,
                    "section": "food",
                    "title": name,
                    "tags": ["맛집", "밥", "식당", str(r.get("area") or ""), name],
                    "facts": [
                        f"{name} · {r.get('area','')} · 대표 {r.get('menu','')} · 팁: {r.get('tip','')} · 위치힌트: {r.get('address_hint','')}"
                    ],
                    "source": "공개 후기·식신 등에서 반복 인용된 실존 상호",
                }
            )
    return cards


def seed_stats(school: str = "") -> dict:
    convs = load_seed_conversations(school)
    cards = iter_fact_cards(school)
    return {
        "conversation_count": len(convs),
        "message_count": sum(len(c.get("messages") or []) for c in convs),
        "fact_card_count": len(cards),
        "school": normalize_school(school) or "(all)",
    }


def _score_blob(question: str, blob: str, *, boost_tokens: list[str] | None = None) -> int:
    q = question.lower()
    b = blob.lower()
    score = 0
    for token in [
        "맛집", "밥", "카페", "김밥", "치킨", "파스타", "순대", "라멘", "돈가스", "초밥",
        "인공", "머신", "딥러닝", "과제", "연구", "논문", "gpu", "전공", "학점", "팀플", "수강",
        "셔틀", "지하철", "버스", "통학", "도서관", "열람", "기숙사", "역",
    ]:
        if token in q and token in b:
            score += 4
    for word in _tokens(question)[:16]:
        if word in b:
            score += 2
    for t in boost_tokens or []:
        if t and t.lower() in q:
            score += 8
        if t and t.lower() in b and any(w in q for w in _tokens(t)[:3]):
            score += 3
    return score


def _score_conversation(question: str, school: str, conv: dict) -> int:
    msgs = conv.get("messages") or []
    blob = f"{conv.get('topic','')} {conv.get('title','')} {conv.get('fact_note','')} " + " ".join(
        str(m.get("text") or "") for m in msgs[:12]
    )
    score = _score_blob(question, blob)
    topic = str(conv.get("topic") or "")
    q = question.lower()
    if "맛집" in topic and any(k in q for k in ("밥", "맛집", "카페", "먹", "식당", "메뉴")):
        score += 8
    if "인공" in topic or "전공" in topic:
        if any(k in q for k in ("인공", "전공", "과제", "머신", "모델", "연구", "학점", "딥러닝")):
            score += 8
    if "캠퍼스" in topic or "통학" in topic:
        if any(k in q for k in ("셔틀", "지하철", "버스", "통학", "도서관", "가는법", "오시는")):
            score += 8
    if school and school in str(conv.get("school") or ""):
        score += 2
    return score


def _score_fact_card(question: str, card: dict) -> int:
    blob = " ".join(
        [
            str(card.get("title") or ""),
            " ".join(str(t) for t in (card.get("tags") or [])),
            " ".join(str(f) for f in (card.get("facts") or [])),
            str(card.get("section") or ""),
        ]
    )
    return _score_blob(question, blob, boost_tokens=list(card.get("tags") or []) + [str(card.get("title") or "")])


def retrieve_conversations(question: str, *, school: str = "", top_k: int = 3) -> list[dict]:
    convs = load_seed_conversations(school)
    if not convs:
        convs = load_seed_conversations("")
    ranked = sorted(convs, key=lambda c: _score_conversation(question, school, c), reverse=True)
    return ranked[: max(1, top_k)]


def retrieve_fact_cards(question: str, *, school: str = "", top_k: int = 4) -> list[dict]:
    cards = iter_fact_cards(school)
    if not cards:
        cards = iter_fact_cards("")
    ranked = sorted(cards, key=lambda c: _score_fact_card(question, c), reverse=True)
    return [c for c in ranked[: max(1, top_k)] if _score_fact_card(question, c) > 0] or ranked[:1]


def format_fact_cards(cards: list[dict], *, max_chars: int = 6000) -> str:
    chunks: list[str] = []
    for card in cards:
        lines = [
            f"### 사실카드 {card.get('id')} | {card.get('school','')} | {card.get('section')} | {card.get('title')}",
        ]
        for fact in card.get("facts") or []:
            lines.append(f"- {fact}")
        chunks.append("\n".join(lines))
    blob = "\n\n".join(chunks)
    return blob[:max_chars] if len(blob) > max_chars else blob


def format_conversations(convs: list[dict], *, max_chars: int = 10000) -> str:
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
    return blob[:max_chars] if len(blob) > max_chars else blob


def _extractive_answer(question: str, school: str, cards: list[dict], convs: list[dict]) -> str:
    """API 키 없을 때 사실 카드로 바로 답한다."""
    canon = normalize_school(school) or "선택 학교"
    if not cards and not convs:
        return f"{canon}에 대한 시드/사실 데이터가 아직 없어요."

    lines = [f"{canon} 기준으로 찾아본 내용이에요."]
    if cards:
        lines.append("")
        for card in cards[:3]:
            lines.append(f"• {card.get('title')}")
            for fact in (card.get("facts") or [])[:3]:
                lines.append(f"  - {fact}")
    if convs:
        lines.append("")
        for conv in convs[:2]:
            lines.append(f"• {conv.get('title')}")
            for m in (conv.get("messages") or [])[:4]:
                lines.append(f"  [{_role_label(str(m.get('senderRole') or ''))}] {m.get('text','')[:120]}")
    lines.append("")
    lines.append("가격·배차·영업은 바뀔 수 있으니 방문 전 한 번 더 확인하세요.")
    return "\n".join(lines)


def answer_school_question(
    question: str,
    *,
    school: str = "",
    messages: list[dict] | None = None,
) -> dict:
    question = (question or "").strip()
    canon = normalize_school(school)
    stats = seed_stats(canon)
    empty = {
        "answer": "질문을 입력해 주세요.",
        "used_message_count": 0,
        "seed_message_count": stats["message_count"],
        "used_conversation_count": 0,
        "seed_conversation_count": stats["conversation_count"],
        "used_fact_count": 0,
        "fact_card_count": stats["fact_card_count"],
        "school": canon or "",
        "source": "empty",
    }
    if not question:
        return empty

    cards = retrieve_fact_cards(question, school=canon, top_k=4)
    picked = retrieve_conversations(question, school=canon, top_k=3)
    used_msgs = sum(len(c.get("messages") or []) for c in picked)

    live = messages or []
    live_note = ""
    if live:
        lines = []
        for item in live[-16:]:
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(f"- [{_role_label(str(item.get('senderRole') or ''))}] {text[:280]}")
        if lines:
            live_note = "\n\n[최근 실제 서비스 채팅 일부]\n" + "\n".join(lines)

    fact_block = format_fact_cards(cards)
    chat_block = format_conversations(picked)
    context = f"[검증된 사실 카드]\n{fact_block}\n\n[선후배 긴 채팅]\n{chat_block}{live_note}"

    base_meta = {
        "used_message_count": used_msgs,
        "seed_message_count": stats["message_count"],
        "used_conversation_count": len(picked),
        "seed_conversation_count": stats["conversation_count"],
        "used_fact_count": len(cards),
        "fact_card_count": stats["fact_card_count"],
        "school": canon or "",
    }

    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {
            **base_meta,
            "answer": _extractive_answer(question, canon, cards, picked),
            "source": "facts",
            "llm_error_type": "missing_api_key",
        }

    school_line = f"대상 학교: {canon}" if canon else "대상 학교: (미지정)"
    system_prompt = f"""
너는 대학 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
아래 **사실 카드**와 **선후배 채팅**만 근거로 답한다. 일반 상식으로 지어내지 마라.
근거에 없으면 "저장된 근거에는 없다"고 말하고, 확인할 공식 페이지/네이버를 안내하라.

규칙:
- 한국어, 구체적(상호·역·출구·메뉴·과목명·배차 힌트).
- {school_line} 맥락 유지. 다른 학교 정보를 섞지 마라.
- 가격·웨이팅·배차는 변동 가능함을 한 줄 고지.
- 출처·인용·근거 목록은 쓰지 말고 자연스러운 답만 한다.
- 개인정보 추론 금지.
"""
    user_prompt = f"""
{context}

[사용자 질문]
{question}
"""
    try:
        def _call():
            model = _model_name()
            base_url = os.getenv("OPENAI_BASE_URL", "").strip().lower()
            # The deployment default includes the OpenRouter provider prefix;
            # the official OpenAI endpoint expects the bare model name.
            if "api.openai.com" in base_url and model.startswith("openai/"):
                model = model.removeprefix("openai/")
            return _client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_prompt.strip()},
                ],
                temperature=0.15,
                max_tokens=1000,
                timeout=65.0,
            )

        # Keep recommendation traffic from occupying every worker and forcing
        # school-bot requests to fall back before they reach the provider.
        future = _school_bot_executor.submit(_call)
        res = future.result(timeout=67.0)
        answer = (res.choices[0].message.content or "").strip() or "답변을 만들지 못했어요."
        return {**base_meta, "answer": answer, "source": "llm+facts"}
    except Exception as e:
        # Never log exception text: provider exceptions can include request
        # details. A class and HTTP status are enough to diagnose safely.
        status = getattr(e, "status_code", None)
        print(f"[school_bot] LLM request failed: {type(e).__name__}, status={status}")
        return {
            **base_meta,
            "answer": _extractive_answer(question, canon, cards, picked)
            + "\n\n(참고: LLM 연결에 실패해 사실 카드 추출 답변으로 대체했습니다.)",
            "source": "facts-fallback",
            "llm_error_type": type(e).__name__,
            "llm_error_status": status,
        }
