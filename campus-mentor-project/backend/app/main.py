"""캠퍼스 선배 매칭 API.

프론트/AI 브랜치와 충돌하지 않도록 backend 아래에서만 동작한다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai.stub_extract import stub_extract  # noqa: E402
from app.schemas import Extraction, MatchRequest, MatchResponse, MentorMatch  # noqa: E402
from matching.matcher import match_mentors  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

app = FastAPI(title="Campus Mentor Matching API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _try_llm_extract(concern_text: str) -> Extraction | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
        from pydantic import BaseModel, Field

        class UserConcernExtraction(BaseModel):
            interests: list[str] = Field(default_factory=list)
            situation: str = ""
            help_fields: list[str] = Field(default_factory=list)

        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=api_key,
        )
        model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "고민글에서 관심사, 상황, 도움 분야를 추출하세요.",
                },
                {"role": "user", "content": concern_text},
            ],
            response_format=UserConcernExtraction,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            return None
        return Extraction.model_validate(parsed.model_dump())
    except Exception:
        return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/match", response_model=MatchResponse)
def create_match(body: MatchRequest) -> MatchResponse:
    if body.extraction is not None:
        extraction = body.extraction
        source = "client"
    elif body.concern_text and body.concern_text.strip():
        llm = _try_llm_extract(body.concern_text.strip())
        if llm is not None:
            extraction = llm
            source = "llm"
        else:
            extraction = Extraction.model_validate(stub_extract(body.concern_text))
            source = "stub"
    else:
        raise HTTPException(
            status_code=400,
            detail="concern_text 또는 extraction 중 하나는 필요합니다.",
        )

    rows = match_mentors(
        interests=extraction.interests,
        help_fields=extraction.help_fields,
        situation=extraction.situation,
        top_k=body.top_k,
    )
    matches = [MentorMatch.model_validate(row) for row in rows]
    return MatchResponse(
        extraction=extraction,
        matches=matches,
        extraction_source=source,
    )
