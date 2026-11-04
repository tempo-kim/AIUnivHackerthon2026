from pydantic import BaseModel, Field


class Extraction(BaseModel):
    interests: list[str] = Field(default_factory=list)
    situation: str = ""
    help_fields: list[str] = Field(default_factory=list)


class ChoiceContext(BaseModel):
    """main.html 선택값 (선택 사항). 고민 문장과 함께 LLM에 힌트로 전달."""

    status: str | None = None
    reason: str | None = None
    detail: str | None = None


class MatchRequest(BaseModel):
    concern_text: str | None = None
    extraction: Extraction | None = None
    choice: ChoiceContext | None = None
    top_k: int = Field(default=3, ge=1, le=10)
    use_llm: bool = True


class MentorMatch(BaseModel):
    mentor_id: str
    display_name: str = ""
    major: str
    experiences: list[str] = Field(default_factory=list)
    help_topics: list[str] = Field(default_factory=list)
    bio: str = ""
    score: float
    reasons: list[str] = Field(default_factory=list)


class MatchResponse(BaseModel):
    extraction: Extraction
    matches: list[MentorMatch]
    extraction_source: str
    mentor_source: str = ""


class MentorOut(BaseModel):
    mentor_id: str
    display_name: str
    major: str
    experiences: list[str]
    help_topics: list[str]
    bio: str = ""


class MentorImportRequest(BaseModel):
    """Syntitan에서 받은 cleaned CSV 전체 텍스트."""

    csv_text: str
