from __future__ import annotations
import atexit
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# backend/.env 파일 경로 설정 및 로드
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# 매칭 추출/추천과 학교봇이 같은 키를 쓰되, 동시 요청 시 서로 대기열에서 굶지 않도록 여유를 둔다.
_llm_executor = ThreadPoolExecutor(max_workers=4)
atexit.register(lambda: _llm_executor.shutdown(wait=False, cancel_futures=True))

# 추천 요청은 화면에서 15초 안에 끝내도록 단일 LLM 호출에 시간 상한을 둔다.
LLM_MATCH_TIMEOUT = min(float(os.getenv("LLM_MATCH_TIMEOUT", "13")), 13.0)
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
    # Do not silently switch to a paid GPT model when Render misses LLM_MODEL.
    if "openrouter.ai" in base_url.lower():
        return "nvidia/nemotron-3.5-super-vl:free"
    raise RuntimeError("LLM_MODEL이 설정되지 않았습니다.")

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
    # OpenRouter의 Nemotron 무료 라우트는 response_format=json_object를
    # 지원하지 않으므로 처음부터 일반 호출로 요청한다. 재시도 문구 판별에
    # 의존하면 제공자 오류 표현이 달라졌을 때 LLM 호출이 그대로 실패할 수 있다.
    normalized_model = model_name.lower().removeprefix("openai/")
    if normalized_model.startswith("nvidia/"):
        return _client().chat.completions.create(**request)

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
너는 대학생 멘토링 서비스의 전문 선배 추천 AI다.
후배의 입력(줄글 + 체크박스)과 후보 선배 목록을 분석하여 가장 적합한 선배를 추천한다.
전달된 후보 목록에 존재하는 mentor_id만 사용하고, 유효한 JSON만 출력한다. 설명, 마크다운, 코드펜스는 절대 출력하지 마라.

[1. 후배 입력 해석 및 우선순위]
후배의 입력은 '줄글'과 '체크박스(원하는 선배 경험 / 받고 싶은 도움 분야)'로 구성된다.
1) 줄글에 구체적인 고민·질문·목표가 있다면 줄글을 최우선 기준으로 삼고, 체크박스는 보조 참고용으로만 쓴다.
2) 줄글이 비어 있거나 모호할 때만 체크박스(특히 '받고 싶은 도움 분야')를 주된 추천 기준으로 삼는다.
3) 줄글과 체크박스가 충돌하면 무조건 줄글을 따른다.

[2. 고민 유형별 매칭 핵심 기준]
① 전공·학업·진로 고민 (전과, 복수전공, 전공공부, 취업, 인턴, 대학원, 공모전 등):
- 후배의 '현재 전공'과 '질문·희망하는 목표 전공'을 반드시 구분해라.
- 목표 전공이 명시되면 해당 학과 선배를 최우선으로 추천하고, 후보에 목표 학과 선배가 있으면 현재 학과가 같다는 이유로 다른 학과 선배를 앞세우지 마라.
- 목표 학과 후보가 없을 때만 인접 전공 선배를 차선으로 추천한다.

② 일상·학교생활 고민 (밥집·맛집·혼밥, 카페·카공, 시간표·수강신청, 기숙사·자취·통학, 동아리·친구·학교적응 등):
- 학과 일치 여부보다 해당 생활 경험과 노하우를 프로필에 구체적으로 적은 선배를 최우선으로 추천한다.
- 인턴·공모전·취업 스펙이 화려하더라도 일상 고민과 무관하면 낮은 점수를 준다.

[3. 의미 기반 확장 매칭]
표면적 단어 일치에만 집착하지 말고 아래 의미적 연결을 적극 인정한다.
- 밥집 추천 ↔ 맛집, 식당, 혼밥, 백반, 야식, 가성비 식당
- 카공 ↔ 공부하기 좋은 카페, 조용한 카페, 콘센트, 와이파이, 밤샘 작업
- 학교적응 ↔ 캠퍼스 생활, 친구 사귀기, 새내기, 동아리, 소모임
- 시간표 ↔ 수강신청, 공강, 연강, 수업 배치, 학점 인정
- 진로·취업 ↔ 직무 탐색, 인턴, 포트폴리오, 자소서, 면접
단순히 같은 학과이거나 학년이 비슷하다는 이유만으로 점수를 높이지 마라.

[4. 적합도 점수(fit) 및 인원 구성 규칙]
후보 전체를 비교해 0~100 정수로 평가한다.
- 85~100: 핵심 고민 또는 목표 전공이 정확히 일치하고 실제 경험이 구체적임
- 65~84: 핵심 고민과 직접 관련되어 실질적 도움이 가능하나 일부 조건(학과·세부경험)이 다름
- 40~64: 인접 분야이거나 간접적으로 참고할 유사 경험 보유
- 0~39: 고민과 관련성이 거의 없음

[추천 인원 규칙]
- 후보가 3명 이상이면 반드시 최종 3명(top_k가 지정되면 top_k명)을 추천한다.
- 원칙적으로 40점 이상 후보 중 상위 순위로 채우되, 40점 이상 후보가 부족할 경우에만 가장 가까운 후보로 부족한 인원을 채우고 reason에 관련성의 한계를 솔직히 밝힌다.

[5. 출력 JSON 형식]
반드시 아래 키 구조와 타입을 정확히 지켜 출력하라.

{
  "interests": ["핵심 키워드 3~6개 (목표 전공, 직무, 생활 키워드 포함)"],
  "situation": "후배의 현재 상황과 실제 도움받고 싶은 목표를 구분해 요약한 한 문장",
  "help_fields": ["학교생활, 전공공부, 진로취업, 인턴대외활동, 대학원연구 중 최대 2개"],
  "suitability": [
    {
      "mentor_id": "후보의 실제 mentor_id",
      "fit": 90,
      "reason": "선배 프로필의 실제 경험과 후배 고민의 연관성을 설명한 한 문장"
    }
  ],
  "recommendations": [
    {
      "mentor_id": "후보의 실제 mentor_id",
      "reason": "후배의 고민과 선배의 구체적 경험이 어떻게 연결되는지 밝힌 추천 이유 한 문장"
    }
  ]
}

[출력 세부 제약]
- suitability는 적합도 높은 순서대로 최대 5명까지 포함한다.
- recommendations는 suitability의 상위 순서와 반드시 일치해야 한다.
- 모든 reason에는 선배 프로필에 실제로 존재하는 전공·활동·경험 소개 내용을 근거로 명시하라.
"""

    request_payload = {
        "concern": concern_text[:2000],
        "candidates": [
            {
                "mentor_id": row.get("mentor_id"),
                "major": row.get("major", ""),
                "status": row.get("status", ""),
                "experiences": list(row.get("experiences") or [])[:4],
                "help_topics": list(row.get("help_topics") or [])[:4],
                "bio": str(row.get("bio") or "")[:120],
            }
            for row in candidates
        ],
        "top_k": min(top_k, len(candidates)),
    }
    model_name = _model_name()
    # Keep candidate context compact enough for one fast, meaningful comparison.
    payload = {
        **request_payload,
        "candidates": request_payload["candidates"][:20],
        "top_k": min(top_k, len(request_payload["candidates"][:20])),
    }
    prompt_text = "아래 JSON을 분석해 지정한 형식으로만 답해.\n" + json.dumps(
        payload, ensure_ascii=False
    )
    try:
        started = time.perf_counter()
        future = _llm_executor.submit(
            _request_llm,
            prompt_text,
            model_name,
            system_prompt,
            timeout=LLM_MATCH_TIMEOUT,
            max_tokens=900,
        )
        res = future.result(timeout=LLM_MATCH_TIMEOUT + 0.5)
        elapsed = time.perf_counter() - started
        print(
            f"[LLM] analyze_and_recommend success candidates={len(payload['candidates'])} elapsed={elapsed:.2f}s"
        )
        content = res.choices[0].message.content if res.choices else ""
        parsed = _parse_match_analysis(content, candidates, top_k)
        if parsed is None:
            raise ValueError("AI 매칭 응답 형식이 올바르지 않습니다.")
        return parsed
    except TimeoutError as exc:
        print(f"[LLM] analyze_and_recommend timeout={LLM_MATCH_TIMEOUT}s")
        print(f"[LLM Error] 추천 분석 타임아웃: {type(exc).__name__}")
    except json.JSONDecodeError as exc:
        print(f"[LLM Error] 매칭 응답 JSON 파싱 에러: {exc}")
    except Exception as exc:
        print(f"[LLM Error] analyze_and_recommend 에러 발생: {exc}")
        traceback.print_exc()

    return None


