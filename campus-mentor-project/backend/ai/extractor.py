"""후배 고민 → JSON 조건 추출 (OpenRouter / OpenAI 호환)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

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
- 모든 추출 결과(키워드, 문장 포함)는 반드시 '한국어(Korean)'로만 작성해야 한다.

* JSON 키:
  - interests: 핵심 관심사 키워드 목록
  - situation: 현재 상황 한 줄 요약
  - help_fields: 선배에게 도움받고 싶은 분야 목록
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
        return {"interests": [], "situation": "JSON 파싱 에러", "help_fields": []}
    except Exception as e:
        print(f"[extractor] {e}")
        return {"interests": [], "situation": "정보 추출 실패", "help_fields": []}


if __name__ == "__main__":
    sample = "수강신청이랑 시간표가 막막한 경영학과 후배입니다."
    print(json.dumps(extract_concern_info(sample), ensure_ascii=False, indent=2))
