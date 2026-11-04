"""뻔뻔하게 — 선배 데이터 + LLM 분석 매칭 API (채팅 제외)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai.extractor import extract_concern_info  # noqa: E402
from ai.stub_extract import stub_extract  # noqa: E402
from app.schemas import (  # noqa: E402
    Extraction,
    MatchRequest,
    MatchResponse,
    MentorImportRequest,
    MentorMatch,
    MentorOut,
)
from matching.matcher import match_mentors  # noqa: E402
from services.mentors import store  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

app = FastAPI(title="뻔뻔하게 Matching API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_concern_text(body: MatchRequest) -> str:
    parts: list[str] = []
    if body.choice:
        if body.choice.status:
            parts.append(f"학적 단계: {body.choice.status}")
        if body.choice.reason:
            parts.append(f"이용 이유: {body.choice.reason}")
        if body.choice.detail:
            parts.append(f"세부 관심: {body.choice.detail}")
    if body.concern_text and body.concern_text.strip():
        parts.append(body.concern_text.strip())
    return "\n".join(parts).strip()


def _extract(body: MatchRequest) -> tuple[Extraction, str]:
    if body.extraction is not None:
        return body.extraction, "client"

    text = _build_concern_text(body)
    if not text:
        raise HTTPException(status_code=400, detail="concern_text 또는 choice/extraction 필요")

    want_llm = body.use_llm and bool(os.getenv("OPENAI_API_KEY", "").strip())
    if want_llm:
        raw = extract_concern_info(text)
        try:
            extraction = Extraction.model_validate(raw)
            if extraction.interests or extraction.help_fields or extraction.situation:
                return extraction, "llm"
        except Exception:
            pass

    return Extraction.model_validate(stub_extract(text)), "stub"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mentors": len(store.list()),
        "mentor_file": str(store.source_path) if store.source_path else None,
        "llm_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
    }


@app.get("/api/mentors", response_model=list[MentorOut])
def list_mentors() -> list[MentorOut]:
    return [MentorOut.model_validate(m.to_dict()) for m in store.list()]


@app.post("/api/mentors/reload")
def reload_mentors() -> dict:
    count = store.reload()
    return {
        "ok": True,
        "count": count,
        "path": str(store.source_path) if store.source_path else None,
    }


@app.post("/api/mentors/import")
def import_mentors(body: MentorImportRequest) -> dict:
    """Syntitan에서 받은 cleaned CSV 텍스트를 반영."""
    try:
        count = store.replace_from_csv_text(body.csv_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "count": count, "path": str(store.source_path)}


@app.post("/api/extract", response_model=Extraction)
def extract_only(body: MatchRequest) -> Extraction:
    extraction, _ = _extract(body)
    return extraction


@app.post("/api/match", response_model=MatchResponse)
def create_match(body: MatchRequest) -> MatchResponse:
    extraction, source = _extract(body)
    rows = match_mentors(
        interests=extraction.interests,
        help_fields=extraction.help_fields,
        situation=extraction.situation,
        mentors=store.as_matching_rows(),
        top_k=body.top_k,
    )
    matches = [MentorMatch.model_validate(row) for row in rows]
    return MatchResponse(
        extraction=extraction,
        matches=matches,
        extraction_source=source,
        mentor_source=str(store.source_path.name) if store.source_path else "",
    )


# ---- 프론트 정적 서빙 (같은 출처에서 열기) ----
if FRONTEND_DIR.exists():
    @app.get("/")
    def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "main.html")

    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
