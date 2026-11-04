"""후배 고민 → JSON 조건 추출 (OpenRouter / OpenAI 호환)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# backend 폴더의 .env 파일 불러오기
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _client() -> OpenAI:
    kwargs = {}
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    return OpenAI(**kwargs)


def extract_concern_info(user_text: str) -> dict:
    system_prompt = """
너는 대학생 멘토링 서비스의 AI 텍스트 분석가야.
후배가 작성한 고민글을 읽고 핵심 정보를 추출해서 JSON으로만 답해.

[주의사항]
- 모든 추출 결과(키워드, 문장 포함)는 반드시 한국어로만 작성해야 한다.
- 영어를 사용하지 마라.

* JSON 키 종류:
  - interests: 고민에서 추출된 핵심 관심사 키워드 목록 (한국어 단어 배열)
  - situation: 현재 처한 상황 한 줄 요약 (한국어 문장)
  - help_fields: 선배에게 도움받고 싶은 분야 목록 (한국어 단어 배열)
"""

    try:
        model_name = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

        res = _client().chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"후배 고민글:\n{user_text}"},
            ],
            temperature=0.1,
        )

        return json.loads(res.choices[0].message.content)

    except json.JSONDecodeError:
        print("⚠️ [오류]: LLM 응답을 JSON으로 파싱하는 데 실패했습니다.")
        return {
            "interests": [],
            "situation": "JSON 파싱 에러",
            "help_fields": [],
        }
    except Exception as e:
        print(f"⚠️ [오류 발생]: {e}")
        return {
            "interests": [],
            "situation": "정보 추출 실패",
            "help_fields": [],
        }


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