import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

# 1. .env 환경변수 로드
load_dotenv()

# 2. OpenRouter 연결 설정 (base_url 지정 필수)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# 3. 추출 구조 정의
class UserConcernExtraction(BaseModel):
    interests: list[str] = Field(description="관심사 키워드 목록")
    situation: str = Field(description="현재 상황 요약")
    help_fields: list[str] = Field(description="도움받고 싶은 분야 목록")

def extract_concern_info(user_text: str) -> dict:
    try:
        # OpenRouter에서 제공하는 모델명 입력 (예: openai/gpt-4o-mini 또는 anthropic/claude-3.5-sonnet 등)
        response = client.beta.chat.completions.parse(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": "고민글에서 관심사, 상황, 도움 분야를 추출하세요."},
                {"role": "user", "content": user_text}
            ],
            response_format=UserConcernExtraction,
        )
        return response.choices[0].message.parsed.model_dump()
    except Exception as e:
        print(f"오류 발생: {e}")
        return {}