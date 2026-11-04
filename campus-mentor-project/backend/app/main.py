"""매칭 API. 고민 추출(extractor/stub)과 선배 CSV 매칭을 한 서버에서 제공한다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai.extractor import extract_concern_info
from ai.stub_extract import stub_extract
from app.schemas import (
    ChoiceContext,
    Extraction,
    MatchRequest,
    MatchResponse,
    MentorImportRequest,
    MentorMatch,
    MentorOut,
)
from matching.matcher import match_mentors
from services.mentors import store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

app = FastAPI(title="뻔뻔하게 매칭")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _str_list(value: object) -> list[str]:
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


def _llm_failed(raw: dict) -> bool:
    situation = str(raw.get("situation") or "")
    return situation in {"정보 추출 실패", "JSON 파싱 에러"} and not _str_list(
        raw.get("interests")
    ) and not _str_list(raw.get("help_fields"))


def _from_llm(raw: dict) -> Extraction:
    return Extraction(
        interests=_str_list(raw.get("interests")),
        situation=str(raw.get("situation") or "").strip(),
        help_fields=_str_list(raw.get("help_fields")),
    )


def _concern_text(concern_text: str | None, choice: ChoiceContext | None) -> str:
    parts: list[str] = []
    body = (concern_text or "").strip()
    if body:
        parts.append(body)
    if choice:
        hint = " · ".join(
            bit.strip()
            for bit in (choice.status, choice.reason, choice.detail)
            if bit and bit.strip()
        )
        if hint and hint not in body:
            parts.append(hint)
    return "\n".join(parts)


def _extract(payload: MatchRequest) -> tuple[Extraction, str]:
    load_dotenv(ENV_PATH, override=True)
    if payload.extraction is not None:
        return payload.extraction, "client"

    text = _concern_text(payload.concern_text, payload.choice)
    if not text:
        raise HTTPException(
            status_code=400,
            detail="concern_text 또는 extraction이 필요합니다.",
        )

    if payload.use_llm and os.getenv("OPENAI_API_KEY", "").strip():
        raw = extract_concern_info(text)
        if not _llm_failed(raw):
            return _from_llm(raw), "llm"

    return Extraction(**stub_extract(text)), "stub"


def _match_response(payload: MatchRequest) -> MatchResponse:
    extraction, source = _extract(payload)
    ranked = match_mentors(
        interests=extraction.interests,
        help_fields=extraction.help_fields,
        situation=extraction.situation,
        mentors=store.as_matching_rows(),
        top_k=payload.top_k,
    )
    mentor_source = store.source_path.name if store.source_path else ""
    return MatchResponse(
        extraction=extraction,
        matches=[MentorMatch(**row) for row in ranked],
        extraction_source=source,
        mentor_source=mentor_source,
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/mentors", response_model=list[MentorOut])
def get_mentors():
    return [MentorOut(**mentor.to_dict()) for mentor in store.list()]


@app.post("/api/mentors/import")
def import_mentors(payload: MentorImportRequest):
    try:
        count = store.replace_from_csv_text(payload.csv_text, save=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": count, "mentor_source": store.source_path.name if store.source_path else ""}


@app.post("/api/mentors/reload")
def reload_mentors():
    try:
        count = store.reload()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="선배 CSV를 찾을 수 없습니다.") from exc
    return {"count": count, "mentor_source": store.source_path.name if store.source_path else ""}


@app.post("/api/extract", response_model=Extraction)
def extract_concern(payload: MatchRequest):
    extraction, _source = _extract(payload)
    return extraction


@app.post("/api/match", response_model=MatchResponse)
def match_mentor(payload: MatchRequest):
    return _match_response(payload)


if FRONTEND_DIR.is_dir():
    app.mount(
        "/frontend",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )
