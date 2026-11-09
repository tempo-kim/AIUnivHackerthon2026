"""후배 고민 → JSON 조건 추출 (OpenRouter / OpenAI 호환)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# backend/.env 파일 경로 설정 및 로드
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)
_llm_executor = ThreadPoolExecutor(max_workers=2)


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    return OpenAI(**kwargs)


def _model_name() -> str:
    configured = os.getenv("LLM_MODEL", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if configured:
        if not base_url and configured.startswith("openai/"):
            return configured.removeprefix("openai/")
        return configured
    return "openai/gpt-4o-mini" if base_url else "gpt-4o-mini"


def _request_llm(user_text: str, model_name: str, system_prompt: str):
    return _client().chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"후배 고민글:\n{user_text}"},
        ],
        temperature=0.1,
        timeout=2.5,
    )


def extract_concern_info(user_text: str) -> dict:
    system_prompt = """
너는 대학생 멘토링 서비스의 AI 텍스트 분석가야.
후배가 작성한 고민글을 읽고 핵심 정보를 추출해서 JSON으로만 답해.

[주의사항]
- 모든 추출 결과(키워드, 문장 포함)는 반드시 한국어로만 작성해야 한다.
- 영어를 사용하지 마라.

- JSON 키 종류:
  - interests: 고민에서 추출된 핵심 관심사 키워드 목록 (한국어 단어 배열)
  - situation: 현재 처한 상황 한 줄 요약 (한국어 문장)
  - help_fields: 아래 표준 분야 중 해당하는 값만 선택한 목록
    - 학교생활
    - 전공공부
    - 진로취업
    - 인턴대외활동
    - 대학원연구
- help_fields에는 위 목록에 없는 표현을 만들지 마라.
- 고민이 여러 분야에 걸치면 최대 2개까지 선택해라.
"""

    try:
        model_name = _model_name()

        future = _llm_executor.submit(_request_llm, user_text, model_name, system_prompt)
        res = future.result(timeout=2.5)

        content = res.choices[0].message.content
        if not content:
            raise ValueError("AI 응답이 비어있습니다.")

        return json.loads(content)

    except json.JSONDecodeError:
        return {
            "interests": [],
            "situation": "JSON 파싱 에러",
            "help_fields": [],
        }
    except Exception:
        return {
            "interests": [],
            "situation": "정보 추출 실패",
            "help_fields": [],
        }


def recommend_mentors(
    *,
    concern_text: str,
    extraction: dict,
    candidates: list[dict],
    top_k: int,
) -> list[dict] | None:
    """규칙 기반 후보를 LLM이 최종 비교·정렬한다."""
    if not candidates:
        return []

    system_prompt = """
너는 대학생 멘토링 서비스의 최종 멘토 추천 담당자야.
후배의 고민과 후보 선배 정보를 비교해 가장 잘 맞는 순서로 추천해.
반드시 JSON 하나만 반환하고 후보에 없는 mentor_id는 절대 만들지 마.
추천 이유는 후보 정보에 근거한 한국어 한 문장으로 작성해.
반환 형식: {"recommendations":[{"mentor_id":"후보 ID","reason":"추천 이유"}]}
"""
    request_payload = {
        "concern": concern_text[:2000],
        "extraction": extraction,
        "candidates": [
            {
                "mentor_id": row.get("mentor_id"),
                "major": row.get("major", ""),
                "experiences": row.get("experiences", []),
                "help_topics": row.get("help_topics", []),
                "bio": str(row.get("bio", ""))[:500],
            }
            for row in candidates
        ],
        "top_k": top_k,
    }
    try:
        model_name = _model_name()
        future = _llm_executor.submit(
            _request_llm,
            json.dumps(request_payload, ensure_ascii=False),
            model_name,
            system_prompt,
        )
        content = future.result(timeout=1.8).choices[0].message.content
        recommendations = json.loads(content or "").get("recommendations")
        if not isinstance(recommendations, list):
            return None

        valid_ids = {str(row.get("mentor_id")) for row in candidates}
        result: list[dict] = []
        seen: set[str] = set()
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            mentor_id = str(item.get("mentor_id") or "")
            reason = str(item.get("reason") or "").strip()
            if mentor_id not in valid_ids or mentor_id in seen or not reason:
                continue
            result.append({"mentor_id": mentor_id, "reason": reason[:200]})
            seen.add(mentor_id)
            if len(result) >= min(top_k, len(candidates)):
                break

        return result or None
    except Exception:
        return None


if __name__ == "__main__":
    test_text = """
    안녕하세요! 저는 2학년 재학 중인 학생인데요,
    이번 학기에 전공 수업을 들으면서 데이터 분석 쪽으로 진로를 잡아야 할지 고민이 커졌어요.
    공부 방식도 잘 모르겠고, 방학 때 인턴십이나 대외활동을 준비해야 할지 감이 안 잡힙니다.
    비슷한 고민을 하셨던 선배님께 진로 탐색이랑 공부 팁을 꼭 듣고 싶어요!
    """

    result = extract_concern_info(test_text)
    print("\n=== AI 추출 결과 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))