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
    experience_preferences: list[str] = Field(default_factory=list)


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
    recommendation_source: str = "rules"
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


class MessageRequest(BaseModel):
    mentorId: str
    senderRole: str
    text: str = Field(min_length=1, max_length=2000)


class EndRequest(BaseModel):
    mentorId: str
    requesterRole: str


class EndResponseRequest(BaseModel):
    mentorId: str
    responderRole: str
    agree: bool


class ReportRequest(BaseModel):
    mentorId: str
    reporterRole: str
    reason: str
    details: str = Field(min_length=1, max_length=4000)


class SchoolBotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    school: str = ""
    history_limit: int = Field(default=80, ge=0, le=200)


class SchoolBotResponse(BaseModel):
    answer: str
    used_message_count: int = 0
    seed_message_count: int = 0
    used_conversation_count: int = 0
    seed_conversation_count: int = 0
    used_fact_count: int = 0
    fact_card_count: int = 0
    citations: list[str] = []
    school: str = ""
    source: str = "llm"
