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

_extract_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("LLM_EXTRACT_WORKERS", "2")))
)
_match_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("LLM_MATCH_WORKERS", "2")))
)
atexit.register(lambda: _extract_executor.shutdown(wait=False, cancel_futures=True))
atexit.register(lambda: _match_executor.shutdown(wait=False, cancel_futures=True))

# 프론트 요청 제한을 고려하되, LLM 응답 시간을 감안해 타임아웃을 넉넉히 늘립니다. (2.5초 -> 15초)
LLM_MATCH_TIMEOUT = float(os.getenv("LLM_MATCH_TIMEOUT", "25"))
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
        started = time.perf_counter()
        future = _extract_executor.submit(
            _request_llm,
            f"후배 고민글:\n{user_text}",
            model_name,
            system_prompt,
            timeout=10.0, # 타임아웃 증가
        )
        res = future.result(timeout=15.0)
        print(f"[LLM] extract_concern_info elapsed={time.perf_counter() - started:.2f}s")

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
후배의 고민과 체크박스, 후보 선배들의 프로필을 종합하여 가장 적합한 선배를 추천한다.

반드시 전달된 후보 목록에 존재하는 선배만 추천하고, 유효한 JSON만 출력한다.
설명, 마크다운, 코드펜스는 출력하지 않는다.
JSON 내부의 설명과 문장은 한국어로 작성한다.

[1. 가장 중요한 추천 원칙]

추천의 가장 중요한 기준은 후배가 실제로 해결하고 싶어 하는 고민이다.

후배의 입력은 다음 두 가지다.
- 줄글: 실제 고민, 질문, 희망 목표를 직접 작성한 내용
- 체크박스: 원하는 선배의 조건과 받고 싶은 도움 분야

두 정보가 모두 존재하면 줄글을 우선한다.
줄글에 구체적인 고민이 있다면 체크박스는 보조적인 참고 정보로만 활용한다.

단, 줄글이 비어 있거나 실질적인 고민을 파악할 수 없는 경우에는 체크박스를 주된 추천 기준으로 활용한다.

체크박스에 선택된 항목이라는 이유만으로 해당 선배를 상위 추천하지 마라.

[2. 후배 고민의 유형과 핵심 목표 파악]

후배의 고민을 크게 두 가지 유형으로 구분한다.

① 전공·학업·진로 고민
- 전공 공부, 전과, 복수전공, 부전공, 진로 탐색, 취업, 인턴, 대학원, 연구, 공모전 등이 포함된다.
- 후배가 실제로 배우고 싶거나 경험을 듣고 싶어 하는 목표 전공과 분야를 파악한다.
- 현재 재학 중인 학과와 목표로 하는 학과를 반드시 구분한다.
- 전과뿐 아니라 복수전공, 부전공, 진로 변경, 단순한 전공 탐색도 동일하게 해석한다.
- 특정 목표 학과가 명확하게 언급되면 해당 학과 선배를 최우선으로 추천한다.
- 후보에 목표 학과 선배가 있다면 현재 학과가 같다는 이유로 다른 선배를 앞세우지 마라.
- 목표 학과가 없다면 실제 고민과 관련된 인접 전공을 고려한다.

② 일상·학교생활 고민
- 밥집, 맛집, 혼밥, 카페, 카공, 시간표, 수강신청, 기숙사, 자취, 통학, 동아리, 친구, 학교적응 등이 포함된다.
- 선배의 학과보다 실제로 보유한 생활 경험과 노하우를 우선한다.
- 후배가 원하는 경험을 프로필에 구체적으로 작성한 선배를 최우선으로 추천한다.
- 인턴, 취업, 공모전 등의 스펙이 화려하더라도 고민과 관련이 없다면 추천 순위를 높이지 마라.

[3. 줄글과 체크박스의 통합 판단]

체크박스는 반드시 다음 두 그룹으로 구분한다.

① 원하는 선배의 경험
- 비슷한 전공
- 비슷한 학년
- 취업 경험
- 인턴 경험
- 대외활동 경험
- 대학원·연구 경험
- 학교생활 경험

② 받고 싶은 도움 분야
- 학교적응
- 밥집 추천
- 전공지식
- 진로와 취업
- 대외활동

줄글에 구체적인 고민이 존재하는 경우 다음 원칙을 적용한다.

- 줄글의 핵심 목표와 직접적으로 관련된 선배를 우선한다.
- 체크박스는 줄글의 목표와 일치하는 경우에만 추천 우선순위를 보완한다.
- 줄글과 충돌하는 체크박스는 추천 순위에 거의 영향을 주지 않도록 한다.
- 체크박스에 선택되지 않은 경험이라도 줄글의 고민을 해결할 수 있다면 적극적으로 추천한다.
- '비슷한 전공'이나 '비슷한 학년'은 선호 조건이지 필수 추천 조건이 아니다.

줄글이 비어 있거나 실질적인 고민이 없는 경우에는 다음 원칙을 적용한다.

- 선택된 도움 분야를 가장 중요한 추천 기준으로 사용한다.
- 해당 분야의 경험을 실제로 보유한 선배를 우선한다.
- 원하는 선배의 경험은 적합한 후보들 사이에서 순위를 정하는 보조 기준으로 활용한다.
- 체크박스도 선택하지 않았다면 선배의 구체적인 경험 소개를 기준으로 추천한다.

[4. 후보 선배 전체 탐색 및 의미 기반 매칭]

전달받은 후보 선배 전체를 검토한 다음 추천 순위를 결정한다.

선배 프로필은 다음 항목을 종합적으로 확인한다.
- 전공
- 학년 및 현재 상태
- 진로 및 활동 경험
- 학교생활 경험
- 경험 소개 및 자기소개
- 도움을 줄 수 있는 분야

표면적인 단어가 동일한지에만 집착하지 말고 의미와 실제 도움 가능성을 판단한다.

다음과 같은 의미적 연결을 인정한다.

- 밥집 추천: 맛집, 식당, 혼밥, 학교 주변 식당, 점심, 저녁, 가성비 식당, 백반, 야식
- 카공: 공부하기 좋은 카페, 조용한 카페, 와이파이, 콘센트, 장시간 공부 공간
- 학교적응: 학교생활, 캠퍼스 생활, 친구 사귀기, 동아리, 대학 생활
- 시간표: 수강신청, 강의 선택, 공강, 수업 배치
- 전공 공부: 전공 과목, 학점 관리, 공부 방법, 기초 과목
- 진로 및 취업: 직무 탐색, 취업 준비, 인턴, 기업 경험, 포트폴리오
- 전과 및 전공 탐색: 목표 학과의 수업, 전공 특성, 학업 경험, 진로 방향

직접적인 단어가 없더라도 실제로 고민 해결에 도움이 되는 경험이라면 관련성이 있다고 판단한다.

반대로 단순히 같은 학과이거나 스펙이 좋다는 이유만으로 관련성이 있다고 판단하지 마라.

[5. 추천 우선순위]

추천 순위는 다음 순서로 판단한다.

1순위: 후배의 구체적인 고민과 직접적으로 일치하는 경험 또는 목표 전공을 보유한 선배
2순위: 핵심 고민과 밀접하게 관련된 유사 경험을 보유한 선배
3순위: 직접적인 경험은 부족하지만 실질적으로 도움을 줄 수 있는 선배

추가 규칙:
- 목표 전공이 명확하면 해당 전공의 선배를 최우선으로 한다.
- 생활 고민이라면 실제 생활 경험을 보유한 선배를 최우선으로 한다.
- 직접적인 관련 경험이 있는 선배가 여러 명이면 경험의 구체성, 다양성, 실제 도움 가능성으로 순위를 정한다.
- 관련 경험이 있는 선배가 후보에 여러 명 존재한다면 가능한 한 해당 선배들을 추천 목록에 포함한다.
- 관련 없는 선배로 추천 자리를 채우지 마라.
- 추천 가능한 적합한 선배가 적다면 적은 인원만 추천해도 된다.
- 후보 목록의 순서나 특정 학과에 편향되지 마라.

[6. 적합도 점수]

각 후보의 적합도를 0~100 정수로 평가한다.

85~100점:
핵심 고민이나 목표 전공이 정확히 일치하고 실제 경험도 충분하다.

65~84점:
핵심 고민과 직접적으로 관련되며 실질적인 도움을 줄 수 있다. 다만 일부 경험이나 조건이 다르다.

40~64점:
인접 분야이거나 간접적으로 참고할 수 있는 경험이 있다.

0~39점:
고민과 관련성이 거의 없거나 실제 도움을 줄 근거가 부족하다.

40점 미만인 선배는 추천 목록에 포함하지 마라.

점수는 체크박스 선택 여부만으로 높이지 말고 실제 경험과 고민의 연관성을 기준으로 결정한다.

[7. 추천 전 최종 검증]

추천 목록을 확정하기 전에 다음 사항을 확인한다.

- 줄글에 명확한 목표가 있다면 해당 목표를 우선했는가?
- 현재 전공과 목표 전공을 혼동하지 않았는가?
- 체크박스의 일반적인 선호가 구체적인 줄글보다 우선되지 않았는가?
- 줄글이 없는 경우 체크박스를 충분히 반영했는가?
- 생활 고민이라면 실제 생활 경험이 있는 선배를 놓치지 않았는가?
- 추천 이유가 실제 프로필 내용으로 뒷받침되는가?
- 고민과 관련 없는 선배가 단순히 추천 인원수를 채우기 위해 들어가지는 않았는가?
- 전달받은 후보 외의 존재하지 않는 선배를 생성하지 않았는가?

[8. 출력 규칙]

반드시 다음 JSON 구조를 유지한다.

{
  "interests": [],
  "situation": "",
  "help_fields": [],
  "suitability": [],
  "recommendations": []
}

각 필드의 작성 기준은 다음과 같다.

interests:
- 핵심 고민 키워드 3~6개
- 목표 전공, 직무, 생활 경험 등 실제 관심사를 포함한다.

situation:
- 후배의 현재 상황과 실제로 도움받고 싶은 내용을 한 문장으로 요약한다.
- 현재 전공과 목표 전공이 다르면 구분한다.

help_fields:
- 다음 항목에서 최대 2개 선택한다.
- 학교생활, 전공공부, 진로취업, 인턴대외활동, 대학원연구

suitability:
- 전체 후보를 비교하고 평가하되 출력은 추천 적합도가 높은 상위 후보만 포함한다.
- mentor_id, fit, reason을 작성한다.
- reason은 실제 프로필 경험과 고민의 연관성을 간결하게 설명한다.
- 적합도 40점 미만은 포함하지 않는다.

recommendations:
- 적합도가 높은 순서대로 최대 top_k명까지 추천한다.
- mentor_id와 reason을 작성한다.
- reason에는 후배의 구체적인 고민과 선배의 실제 경험이 어떻게 연결되는지 설명한다.
- 추천할 만한 후보가 부족하면 인원을 억지로 채우지 않는다.
- suitability의 순위와 recommendations의 순위는 일치해야 한다.

mentor_id는 반드시 전달된 후보의 실제 값을 그대로 사용한다.
모든 점수는 정수로 작성한다.
JSON 외의 어떠한 문장도 출력하지 않는다.
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
    attempts = [
        {
            "timeout": LLM_MATCH_TIMEOUT,
            "max_tokens": 2200,
            "candidates": request_payload["candidates"],
        },
        {
            "timeout": LLM_MATCH_TIMEOUT + 10.0,
            "max_tokens": 1600,
            "candidates": request_payload["candidates"][: max(20, min(50, len(request_payload["candidates"])) )],
        },
    ]

    for index, attempt in enumerate(attempts, 1):
        try:
            payload = {
                **request_payload,
                "candidates": attempt["candidates"],
                "top_k": min(top_k, len(attempt["candidates"])),
            }
            prompt_text = "아래 JSON을 분석해 지정한 형식으로만 답해.\n" + json.dumps(
                payload, ensure_ascii=False
            )
            started = time.perf_counter()
            future = _match_executor.submit(
                _request_llm,
                prompt_text,
                model_name,
                system_prompt,
                timeout=attempt["timeout"],
                max_tokens=attempt["max_tokens"],
            )
            res = future.result(timeout=attempt["timeout"] + 1.0)
            elapsed = time.perf_counter() - started
            print(
                f"[LLM] analyze_and_recommend success attempt={index} candidates={len(attempt['candidates'])} elapsed={elapsed:.2f}s"
            )

            content = res.choices[0].message.content if res.choices else ""
            parsed = _parse_match_analysis(content, candidates, top_k)
            if parsed is None:
                raise ValueError("AI 매칭 응답 형식이 올바르지 않습니다.")
            return parsed
        except TimeoutError as exc:
            print(
                f"[LLM] analyze_and_recommend timeout attempt={index} candidates={len(attempt['candidates'])} timeout={attempt['timeout']}"
            )
            if index == len(attempts):
                print(f"[LLM Error] analyze_and_recommend 최종 타임아웃: {exc}")
            continue
        except json.JSONDecodeError as exc:
            print(f"[LLM Error] 매칭 응답 JSON 파싱 에러: {exc}")
            break
        except Exception as exc:
            print(f"[LLM Error] analyze_and_recommend 에러 발생: {exc}")
            traceback.print_exc()
            break

    return None


