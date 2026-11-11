"""후배 고민 분석과 선배 추천을 OpenRouter 호출 한 번으로 처리한다."""

from __future__ import annotations

import atexit
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
atexit.register(lambda: _llm_executor.shutdown(wait=False, cancel_futures=True))
# 프론트 요청 제한(5초) 안에서 분석과 최종 추천을 한 응답으로 끝낸다.
LLM_MATCH_TIMEOUT = 4.5
ALLOWED_HELP_FIELDS = (
    "학교생활",
    "전공공부",
    "진로취업",
    "인턴대외활동",
    "대학원연구",
)


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
    configured = os.getenv("LLM_MODEL", "").split("#", 1)[0].strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if configured:
        if not base_url and configured.startswith("openai/"):
            return configured.removeprefix("openai/")
        return configured
    return "openai/gpt-4o-mini" if base_url else "gpt-4o-mini"


def _request_llm(
    user_text: str,
    model_name: str,
    system_prompt: str,
    *,
    timeout: float = 2.5,
    max_tokens: int = 500,
):
    return _client().chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _fit_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(100.0, score)), 2)


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

        future = _llm_executor.submit(
            _request_llm,
            f"후배 고민글:\n{user_text}",
            model_name,
            system_prompt,
        )
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


def _parse_match_analysis(content: str, candidates: list[dict], top_k: int) -> dict | None:
    """한 응답에서 키워드, 상황, 후보 적합도, 상위 추천을 꺼낸다."""
    data = json.loads(content or "")
    if not isinstance(data, dict):
        return None

    valid_ids = {str(row.get("mentor_id")) for row in candidates if row.get("mentor_id")}
    limit = min(top_k, len(valid_ids))
    interests = _string_list(data.get("interests"))[:6]
    situation = str(data.get("situation") or "").strip()[:200]
    help_fields: list[str] = []
    for field in _string_list(data.get("help_fields")):
        if field in ALLOWED_HELP_FIELDS and field not in help_fields:
            help_fields.append(field)
        if len(help_fields) >= 2:
            break

    suitability: list[dict] = []
    seen_fit: set[str] = set()
    raw_suitability = data.get("suitability")
    if isinstance(raw_suitability, list):
        for item in raw_suitability:
            if not isinstance(item, dict):
                continue
            mentor_id = str(item.get("mentor_id") or "")
            reason = str(item.get("reason") or "").strip()[:200]
            if mentor_id not in valid_ids or mentor_id in seen_fit or not reason:
                continue
            suitability.append(
                {"mentor_id": mentor_id, "fit": _fit_score(item.get("fit")), "reason": reason}
            )
            seen_fit.add(mentor_id)

    recommendations: list[dict] = []
    seen_rank: set[str] = set()
    raw_recommendations = data.get("recommendations")
    if isinstance(raw_recommendations, list):
        for item in raw_recommendations:
            if not isinstance(item, dict):
                continue
            mentor_id = str(item.get("mentor_id") or "")
            reason = str(item.get("reason") or "").strip()[:200]
            if mentor_id not in valid_ids or mentor_id in seen_rank or not reason:
                continue
            recommendations.append({"mentor_id": mentor_id, "reason": reason})
            seen_rank.add(mentor_id)
            if len(recommendations) >= limit:
                break

    if len(recommendations) < limit:
        for item in sorted(suitability, key=lambda row: row["fit"], reverse=True):
            if item["mentor_id"] in seen_rank:
                continue
            recommendations.append({"mentor_id": item["mentor_id"], "reason": item["reason"]})
            seen_rank.add(item["mentor_id"])
            if len(recommendations) >= limit:
                break

    if not recommendations:
        return None

    return {
        "interests": interests,
        "situation": situation,
        "help_fields": help_fields,
        "suitability": suitability,
        "recommendations": recommendations,
    }


def analyze_and_recommend(
    *,
    concern_text: str,
    candidates: list[dict],
    top_k: int,
) -> dict | None:
    """고민 키워드·상황 요약·후보 적합도·상위 추천·이유를 한 번의 LLM 호출로 받는다."""
    if not candidates:
        return {
            "interests": [],
            "situation": "",
            "help_fields": [],
            "suitability": [],
            "recommendations": [],
        }

    system_prompt = """
너는 대학생 멘토링 서비스의 분석·추천 담당자야.
후배 고민과 후보 선배 목록을 읽고 JSON 하나만 반환해.
설명, 마크다운, 코드펜스는 붙이지 마. 모든 문장과 키워드는 한국어로만 작성해.

[필드]
- interests: 고민 핵심 키워드 3~6개
- situation: 현재 상황 한 줄 요약
- help_fields: 학교생활, 전공공부, 진로취업, 인턴대외활동, 대학원연구 중에서만 최대 2개
- suitability: 전달된 후보 전원. mentor_id, fit(0~100 숫자), reason(후보 근거 한 문장)
- recommendations: suitability가 높은 순서의 상위 인원. mentor_id, reason(추천 이유 한 문장)
  배열 순서가 최종 순위다. 후보에 없는 mentor_id는 만들지 마.

반환 형식:
{"interests":[],"situation":"","help_fields":[],"suitability":[{"mentor_id":"","fit":0,"reason":""}],"recommendations":[{"mentor_id":"","reason":""}]}
"""
    request_payload = {
        "concern": concern_text[:2000],
        "candidates": [
            {
                "mentor_id": row.get("mentor_id"),
                "major": row.get("major", ""),
                "status": row.get("status", ""),
                "experiences": list(row.get("experiences") or [])[:6],
                "help_topics": list(row.get("help_topics") or [])[:6],
                "bio": str(row.get("bio") or "")[:180],
            }
            for row in candidates
        ],
        "top_k": min(top_k, len(candidates)),
    }
    user_text = "아래 JSON을 분석해 지정한 형식으로만 답해.\n" + json.dumps(
        request_payload, ensure_ascii=False
    )
    try:
        model_name = _model_name()
        future = _llm_executor.submit(
            _request_llm,
            user_text,
            model_name,
            system_prompt,
            timeout=LLM_MATCH_TIMEOUT,
            max_tokens=900,
        )
        content = future.result(timeout=LLM_MATCH_TIMEOUT).choices[0].message.content
        return _parse_match_analysis(content or "", candidates, top_k)
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