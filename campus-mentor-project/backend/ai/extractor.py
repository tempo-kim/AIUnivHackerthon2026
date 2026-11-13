from __future__ import annotations
import atexit
import json
import os
import traceback
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

# 프론트 요청 제한을 고려하되, LLM 응답 시간을 감안해 타임아웃을 넉넉히 늘립니다. (2.5초 -> 15초)
LLM_MATCH_TIMEOUT = 15.0  
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
    timeout: float = 10.0, # 기본 타임아웃 10초로 증가
    max_tokens: int = 500,
):
    request = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    try:
        return _client().chat.completions.create(
            **request,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        message = str(exc).lower()
        if not any(
            phrase in message
            for phrase in ("response_format", "json_object", "unsupported", "not support")
        ):
            raise
        return _client().chat.completions.create(**request)

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
    # 기존 프롬프트 유지
    system_prompt = """
당신은 후배의 고민을 분석하는 전문 AI 시스템입니다.

[응답 형식]
반드시 다음 구조의 JSON만 반환하세요:
{
  "interests": ["관심 분야 키워드1", "키워드2"],
  "situation": "후배의 핵심 고민 상황 요약",
  "help_fields": ["도움받고 싶은 분야1", "분야2"]
}
"""
    try:
        model_name = _model_name()
        future = _llm_executor.submit(
            _request_llm,
            f"후배 고민글:\n{user_text}",
            model_name,
            system_prompt,
            timeout=10.0, # 타임아웃 증가
        )
        res = future.result(timeout=15.0)

        content = res.choices[0].message.content
        if not content:
            raise ValueError("AI 응답이 비어있습니다.")

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"[LLM Error] JSON 파싱 에러: {e}")
        return {"interests": [], "situation": "JSON 파싱 에러", "help_fields": []}
    except Exception as e:
        print(f"[LLM Error] extract_concern_info 에러 발생: {e}")
        traceback.print_exc()
        return {"interests": [], "situation": "정보 추출 실패", "help_fields": []}

def _parse_match_analysis(content: str, candidates: list[dict], top_k: int) -> dict | None:
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
    if not candidates:
        return {
            "interests": [],
            "situation": "",
            "help_fields": [],
            "suitability": [],
            "recommendations": [],
        }

    # 여기에 실제 매칭 로직과 평가 기준 프롬프트를 명확히 주입합니다.
    system_prompt = """
너는 대학생 멘토링 서비스의 분석·추천 담당자다.
후배 고민(체크박스 내용 + 줄글)과 후보 선배 목록을 읽고 최적의 선배를 매칭해라.
설명, 마크다운, 코드펜스는 붙이지 마라. 모든 문장과 키워드는 한국어로만 작성해라.

[고민 유형 분류 및 우선순위 기준]
먼저 후배의 고민이 아래 두 유형 중 어디에 해당하는지 판단해라.

1. 전공·진로·학업 고민 (전과, 복수전공, 전공공부, 인턴, 취업, 대학원, 공모전 등):
  - 줄글에서 후배가 실제로 답을 얻고 싶은 목표 전공·직무·활동 및 전과/진로 변경 의도를 최우선으로 추출해라.
  - 현재 전공이 앞부분에 나오더라도 "전과하려 한다", "궁금하다", "이야기를 듣고 싶다"처럼 질문·희망의 대상이 되는 전공을 최우선 목표로 해석해라. (예: 컴공 재학 중 화공과 전과 희망 → 화공과 선배 최우선)
  - 줄글에 특정 학과가 명시되면 해당 학과 선배를 최우선 추천하고, 후보에 해당 학과가 있으면 유사 학과를 앞세우지 마라.
  - 목표 전공 후보가 없을 때만 인접 전공을 보완 후보로 사용해라.

2. 일상·학교생활 고민 (밥집, 맛집, 카페, 카공, 수강신청, 시간표, 기숙사, 자취, 통학, 동아리, 친구 사귀기, 학교적응 등):
  - 일상·캠퍼스 생활 질문은 특정 학과 지정이 없는 한 학과 일치 여부보다 '해당 생활 경험의 일치도'를 최우선으로 평가해라.
  - 학과가 다르더라도 후배가 찾는 생활 노하우(예: 카공 명당, 혼밥 밥집, 통학 시간표, 기숙사 생활, 편입 학점 인정 등)를 경험 소개에 보유한 선배에게 최고점을 부여해라.
  - 스펙(인턴, 공모전, 랩실 등)이 화려하더라도 일상·학교생활 고민과 무관한 선배는 낮은 점수를 주고 추천에서 배제해라.

[의미 기반 매칭 및 나쁜 매칭 금지]
- 표면적 단어 일치에만 집착하지 말고 문맥과 의도가 통하면 적극 매칭해라. (예: '밤늦게 공부할 카페' ↔ '카공', '혼자 먹을 식당' ↔ '혼밥/밥집', '수업 배치' ↔ '시간표/수강신청')
- 체크박스 선호는 줄글의 목표와 함께 고려하되, 줄글의 명시적 목표·질문 대상을 덮어쓰지 못한다.
- 후배의 고민과 연관성이 전혀 없는 선배, 이름값·스펙만 높은 선배, 단순히 같은 학년이라는 이유만의 추천은 엄격히 금지한다.

[fit 점수 산정 기준 (0~100)]
- 85~100: 핵심 고민/생활 경험이 정확히 일치하며, 전공·상황 조건까지 완벽히 부합
- 65~84: 핵심 고민/생활 경험이 일치하나 전공이 다르거나, 목표 전공은 일치하나 세부 경험이 간접적임
- 40~64: 인접 분야이거나 부분적으로 참고 가능한 유사 경험을 보유함
- 0~39: 후배의 고민과 연관성이 거의 없음 (recommendations 포함 금지)

[출력 필드 규칙]
- interests: 고민 핵심 키워드 3~6개 (목표 전공·직무·생활 키워드 및 전과/진로 의도 포함)
- situation: 현재 상황 한 줄 요약 (현재 전공과 최종 질문·희망 대상을 구분하여 작성)
- help_fields: ["학교생활", "전공공부", "진로취업", "인턴대외활동", "대학원연구"] 중에서만 최대 2개 선택
- suitability: 전달된 후보 전원 평가. mentor_id, fit(위 기준에 따른 0~100 정수), reason(선배 프로필의 실제 경험·전공을 근거로 한 평가 한 문장)
- recommendations: suitability의 fit이 높은 순서대로 상위 인원(fit 40 미만 제외). mentor_id, reason(후배의 어떤 고민 키워드와 선배의 어떤 프로필 내용이 일치/유사한지 구체적 근거를 밝힌 추천 이유). 배열 순서가 최종 순위이며, 후보에 없는 mentor_id는 절대 생성하지 마라.

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
            timeout=LLM_MATCH_TIMEOUT, # 늘어난 타임아웃 적용
            max_tokens=3000,
        )
        res = future.result(timeout=LLM_MATCH_TIMEOUT + 1.0)
        content = res.choices[0].message.content if res.choices else ""
        parsed = _parse_match_analysis(content, candidates, top_k)
        if parsed is None:
            raise ValueError("AI 매칭 응답 형식이 올바르지 않습니다.")
        return parsed
    except json.JSONDecodeError as exc:
        print(f"[LLM Error] 매칭 응답 JSON 파싱 에러: {exc}")
    except Exception as exc:
        print(f"[LLM Error] analyze_and_recommend 에러 발생: {exc}")
        traceback.print_exc()
    return None


