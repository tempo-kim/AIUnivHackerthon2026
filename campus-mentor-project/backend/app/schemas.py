from pydantic import BaseModel, Field


class Extraction(BaseModel):
    """AI 추출 결과와 같은 필드. AI/extraction 브랜치 extractor와 맞춤."""

    interests: list[str] = Field(default_factory=list, description="관심사 키워드")
    situation: str = Field(default="", description="현재 상황 요약")
    help_fields: list[str] = Field(default_factory=list, description="도움 분야")


class MatchRequest(BaseModel):
    """고민 원문 또는 이미 추출된 조건 중 하나를 보냄."""

    concern_text: str | None = Field(default=None, description="후배 고민 원문")
    extraction: Extraction | None = Field(default=None, description="이미 추출된 조건")
    top_k: int = Field(default=3, ge=1, le=10)


class MentorMatch(BaseModel):
    mentor_id: str
    major: str
    experiences: list[str]
    help_topics: list[str]
    score: float
    reasons: list[str]


class MatchResponse(BaseModel):
    extraction: Extraction
    matches: list[MentorMatch]
    extraction_source: str = Field(description="llm | stub | client")
