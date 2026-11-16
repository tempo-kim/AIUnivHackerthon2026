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

[후보 선배 전체 탐색 및 경험 기반 매칭 강화 규칙]

일상·학교생활 고민에서는 후보 선배 목록 전체를 반드시 탐색하고, 후배가 원하는 경험을 실제로 보유한 선배를 빠짐없이 찾아라.

1. 후보 전체 탐색
- 추천 순위를 결정하기 전에 전달받은 전체 후보 선배의 진로 경험, 학교 활동 경험, 경험 소개를 모두 확인해라.
- 선배의 학과나 진로 경험만 보고 적합성을 판단하지 마라.
- 특히 경험 소개에 작성된 구체적인 생활 경험과 노하우를 가장 중요한 매칭 근거로 활용해라.
- 후보 목록 앞부분에 있는 선배나 특정 학과 선배만 편향적으로 선택하지 마라.

2. 의미 기반 경험 추출
- 후배가 요청한 경험과 의미적으로 관련된 표현을 폭넓게 탐색해라.
- 예를 들어 밥집 추천 요청은 밥집, 맛집, 식당, 혼밥, 1인 식당, 백반집, 학교 앞 식당, 점심 메뉴, 저녁 메뉴, 가성비 식당, 야식 등의 표현을 모두 관련 경험으로 인정해라.
- '혼자 먹기 좋은 곳'은 혼밥 경험과 연결하고, '가성비 좋은 식당'은 저렴한 밥집 경험과 연결해라.
- 동일한 단어가 포함되어 있지 않더라도 실제로 후배의 고민 해결에 도움이 되는 경험이라면 매칭 대상에 포함해라.

3. 관련 경험 보유자 우선 추천
- 후배가 특정 생활 경험을 요청했다면 해당 경험을 직접 보유한 선배를 최우선으로 추천해라.
- 해당 경험을 직접 보유한 선배가 여러 명이면 관련 경험의 구체성, 다양성, 경험 기간 및 실제 도움 가능성을 기준으로 순위를 결정해라.
- 선배의 학과, 학년, 인턴, 공모전, 취업 등의 스펙은 요청한 생활 경험과 직접적인 관련이 없는 한 우선순위를 높이는 근거로 사용하지 마라.
- 관련 경험을 보유한 선배가 후보에 존재하는데도 관련성이 낮은 선배를 추천 목록에 포함하지 마라.

4. 추천 인원 구성
- 추천 가능한 인원수 내에서 후배의 고민과 관련된 경험을 가진 선배를 최대한 우선적으로 구성해라.
- 관련 경험을 보유한 선배가 5명이라면 그중 적합도가 높은 순서대로 추천해라.
- 관련 경험이 있는 선배를 한 명만 찾았다는 이유로 나머지 추천 자리를 관련성이 낮은 선배로 채우지 마라.
- 추천 가능한 관련 경험 보유자가 추천 인원보다 적다면 관련 없는 선배를 억지로 추가하지 말고 실제 적합한 선배만 추천해라.

5. 추천 전 최종 검증
- 추천 목록을 확정하기 전에 후보 전체에서 요청한 경험을 보유한 선배를 놓치지 않았는지 다시 확인해라.
- 각 추천 선배에 대해 후배가 요청한 내용과 직접 연결되는 구체적인 경험 소개가 존재하는지 검증해라.
- 단순히 '학교생활 경험 일치'라는 포괄적인 이유만으로 추천하지 마라. 반드시 어떤 경험이 일치하는지 근거를 제시해라.


[의미 기반 매칭 및 나쁜 매칭 금지]
- 표면적 단어 일치에만 집착하지 말고 문맥과 의도가 통하면 적극 매칭해라. (예: '밤늦게 공부할 카페' ↔ '카공', '혼자 먹을 식당' ↔ '혼밥/밥집', '수업' ↔ '시간표/수강신청')
- 체크박스 선호는 줄글의 목표와 함께 고려하되, 줄글의 명시적 목표·질문 대상을 덮어쓰지 못한다.
- 후배의 고민과 연관성이 전혀 없는 선배, 이름값·스펙만 높은 선배, 단순히 같은 학년이라는 이유만의 추천은 엄격히 금지한다.

[현재 전공과 목표 전공의 구분 및 핵심 관심사 파악 규칙]

전공·진로·학업 고민에서는 후배가 언급한 모든 학과를 동일한 비중으로 취급하지 마라. 반드시 문맥을 분석하여 '현재 소속 전공'과 '실제로 도움받고 싶어 하는 목표 전공'을 구분해라.

1. 현재 전공과 목표 전공 구분
- 현재 전공은 후배가 현재 재학 중인 학과를 의미한다.
- 목표 전공은 후배가 진입하고 싶거나, 배우고 싶거나, 정보를 얻고 싶거나, 선배의 경험을 듣고 싶어 하는 학과를 의미한다.
- 목표 전공은 전과, 복수전공, 부전공, 진로 변경, 전공 탐색 등 어떤 목적이든 해당할 수 있다.

2. 문맥과 의도를 기반으로 목표 전공 추출
- "~학과로 전과하고 싶다", "~학과를 복수전공하고 싶다", "~학과에 관심이 있다", "~학과 선배의 경험을 듣고 싶다" 등의 표현에서 실제 관심과 질문의 대상이 되는 학과를 파악해라.
- 한 문장에 현재 전공과 목표 전공이 동시에 등장하면, 단순히 먼저 언급된 학과나 체크박스에 표시된 학과를 우선하지 마라.
- 후배가 궁극적으로 알고 싶어 하는 내용과 도움받고 싶어 하는 대상 학과를 최우선으로 판단해라.
- 여러 학과가 등장하더라도 실제 고민 해결에 필요한 핵심 목표 전공을 하나 이상 식별해라.

3. 목표 전공 중심의 추천 우선순위
- 후배가 명확하게 관심을 표현한 목표 전공과 동일한 학과의 선배가 후보 목록에 존재하면 해당 학과 선배를 최우선으로 추천해라.
- 목표 전공과 일치하는 선배가 후보 목록에 존재한다면, 단순히 현재 전공이 같다는 이유로 다른 학과 선배를 우선 추천하지 마라.
- 체크박스의 전공 일치 여부보다 줄글에서 드러나는 구체적인 관심 전공과 질문 의도를 우선해라.
- 목표 전공과 일치하는 선배가 여러 명이면 해당 전공에서의 학업 경험, 진로 경험, 활동 경험 등을 비교하여 순위를 결정해라.
- 목표 전공에 해당하는 선배가 후보 목록에 없을 때만 관련성이 높은 인접 전공이나 현재 전공의 선배를 대안으로 고려해라.

4. 예외 상황
- 후배가 현재 전공 자체에 대한 학업 고민을 이야기한다면 현재 전공의 선배를 우선 추천해라.
- 특정 목표 전공 없이 여러 학과를 탐색하거나 비교하고 싶어 한다면 언급된 학과들의 관련 경험을 가진 선배를 추천해라.
- 목표 전공이 명확하지 않다면 임의로 추측하지 말고 체크박스와 줄글을 종합하여 가장 가능성 높은 관심 분야를 판단해라.

핵심 원칙: 선배 추천은 후배의 현재 소속 학과가 아니라, 후배가 실제로 알고 싶어 하고 도움받고 싶어 하는 분야를 기준으로 결정해야 한다.

[체크박스와 줄글의 우선순위 및 통합 분석 규칙]

후배의 입력은 두 종류로 구성된다.

1. 체크박스: 후배가 원하는 선배의 경험 및 도움 분야를 선택한 정보
2. 줄글: 후배가 실제로 해결하고 싶은 고민, 구체적인 질문, 희망 목표를 직접 작성한 정보

두 정보는 모두 추천에 활용하되, 줄글의 구체적인 내용이 체크박스의 일반적인 선택보다 우선한다.

1. 줄글과 체크박스의 우선순위

- 줄글에 구체적이고 명확한 고민이나 질문이 작성되어 있다면 줄글을 최우선으로 분석해라.
- 줄글의 추천 반영 비중은 약 80%, 체크박스는 약 20%를 기준으로 판단해라.
- 체크박스는 줄글에서 파악한 고민을 보완하고, 적합한 선배들 사이에서 우선순위를 결정하는 참고 자료로 활용해라.
- 체크박스에 선택된 항목이 줄글의 구체적인 목표와 충돌한다면 반드시 줄글의 목표를 우선해라.
- 체크박스에 선택된 항목이라는 이유만으로 해당 경험을 가진 선배를 상위 추천하지 마라.
- 줄글에서 드러난 실제 고민과 관련성이 낮은 체크박스 항목은 추천 우선순위에 큰 영향을 주지 않도록 해라.

2. 두 종류의 체크박스 구분

체크박스는 다음 두 그룹으로 나누어 해석해라.

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

두 그룹의 선택 항목을 모두 고려하되, 줄글에서 구체적으로 드러난 고민을 해결하는 데 실제로 도움이 되는지를 기준으로 활용해라.

특히 '원하는 선배의 경험'은 선배의 조건에 대한 선호이지, 반드시 해당 조건을 가진 선배를 추천해야 한다는 강제 조건이 아니다.

예를 들어 '비슷한 전공'을 선택했더라도 줄글에서 밥집 추천을 요청했다면 전공이 같은 선배보다 밥집과 맛집 경험을 보유한 선배를 우선 추천해라.

3. 줄글과 체크박스가 서로 다른 경우

- 줄글에 특정 전공, 직무, 생활 경험, 활동 등이 구체적으로 명시되면 해당 목표와 직접적으로 일치하는 선배를 우선 추천해라.
- 체크박스의 선택 항목이 줄글의 목표와 일치하지 않는다면 해당 체크박스의 영향력을 낮춰라.
- 체크박스와 줄글이 일치한다면 두 정보를 함께 활용하여 추천 적합도를 높여라.
- 줄글에 구체적인 목표가 있다면 체크박스에 해당 항목이 선택되지 않았더라도 관련 경험을 가진 선배를 추천 대상에서 제외하지 마라.

4. 줄글이 없거나 구체적인 고민이 작성되지 않은 경우

- 줄글이 비어 있거나, 단순한 인사말 또는 실질적인 고민 파악이 어려운 짧은 문장만 작성되어 있다면 체크박스를 중심으로 추천해라.
- 이 경우 체크박스의 반영 비중을 100%로 높여라.
- '원하는 선배의 경험'과 '받고 싶은 도움 분야' 두 그룹을 모두 활용해라.
- 선택된 도움 분야와 직접적으로 관련된 경험을 보유한 선배를 우선 추천하고, 원하는 선배의 경험은 적합한 선배들 사이의 순위를 결정하는 보조 기준으로 사용해라.
- 체크박스도 선택하지 않았다면 선배의 구체적인 경험 소개를 기준으로 폭넓게 추천해라.

5. 실제 매칭 예시

예시 1.
체크박스: 비슷한 전공, 취업 경험
도움 분야: 밥집 추천
줄글: 학교 근처에서 혼자 밥 먹기 좋은 맛집을 추천받고 싶어요.

→ 혼밥, 학교 주변 식당, 맛집 경험을 가진 선배를 최우선 추천한다.
→ 컴퓨터공학과라는 이유나 취업 경험만으로 해당 선배를 우선 추천하지 마라.

예시 2.
체크박스: 비슷한 전공, 취업 경험
도움 분야: 전공지식, 진로와 취업
줄글: 컴퓨터공학과에서 경영학과로 진로를 변경하고 싶은데 경영학과에서는 어떤 공부를 하고 어떤 진로로 나아가는지 궁금해요.

→ 경영학과 선배를 최우선 추천한다.
→ 현재 전공과 동일한 선배라는 이유로 컴퓨터공학과 선배를 우선 추천하지 마라.

예시 3.
체크박스: 비슷한 전공, 인턴 경험
도움 분야: 진로와 취업
줄글: 작성하지 않음.

→ 체크박스를 중심으로 컴퓨터공학과 선배 중 인턴 및 취업 경험이 있는 선배를 우선 추천한다.

6. 최종 추천 전 검증

- 추천을 확정하기 전에 줄글의 핵심 고민과 체크박스 선택 항목이 각각 어떤 역할을 하는지 구분해라.
- 줄글에 구체적인 목표가 있다면 추천 선배가 해당 목표를 실제로 해결하는 데 도움이 되는지 우선 검증해라.
- 체크박스의 일반적인 조건이 줄글의 구체적인 목표보다 높은 우선순위로 적용되지 않았는지 확인해라.
- 줄글이 없는 경우에는 체크박스가 충분히 반영되었는지 확인해라.

핵심 원칙: 체크박스는 후배의 선호를 파악하는 보조 정보이고, 줄글은 후배가 실제로 원하는 도움을 파악하는 핵심 정보다. 단, 줄글이 없거나 실질적인 고민을 파악할 수 없는 경우에는 체크박스를 주된 추천 기준으로 활용해라.

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


