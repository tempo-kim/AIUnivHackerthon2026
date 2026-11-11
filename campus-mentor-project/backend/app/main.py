"""매칭 API. 고민 추출(extractor/stub)과 선배 CSV 매칭을 한 서버에서 제공한다."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai.extractor import analyze_and_recommend, extract_concern_info
from ai.stub_extract import stub_extract
from app.schemas import (
    ChoiceContext,
    Extraction,
    MatchRequest,
    MatchResponse,
    MentorImportRequest,
    MentorMatch,
    MentorOut,
    EndRequest,
    EndResponseRequest,
    MessageRequest,
    ReportRequest,
)
from matching.matcher import match_mentors
from services import storage
from services.badwords import contains_badword
from services.mentors import Mentor, store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

load_dotenv(ENV_PATH, override=False)
configured_origins = os.getenv("FRONTEND_ORIGIN", "").strip()
allowed_origins = [
    origin.strip()
    for origin in configured_origins.split(",")
    if origin.strip()
]
if not allowed_origins:
    allowed_origins = ["http://127.0.0.1:8000", "http://localhost:8000"]

app = FastAPI(title="뻔뻔하게 매칭")

_register_lock = threading.Lock()
_login_fails: dict[str, dict] = {}  # 닉네임별 {"count": 연속 실패 수, "until": 잠금 해제 시각}
_login_lock = threading.Lock()
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 300
PIN_PATTERN = re.compile(r"[0-9]{4,6}")


def _restore_registered() -> None:
    """DB에 저장된 등록 선배를 매칭 store에 다시 넣는다(이미 있는 ID는 건너뜀)."""
    known = {mentor.mentor_id for mentor in store.list()}
    for row in storage.list_mentors():
        if row["mentor_id"] in known:
            continue
        # MentorStore에는 ID를 지정해 넣는 함수가 없어 목록에 직접 추가한다
        store._mentors.append(Mentor(experiences=[], help_topics=[], **row))


storage.init()
_restore_registered()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


JUNIOR_ID_PATTERN = re.compile(r"J-[A-Za-z0-9]{8}")


# juniorId가 빠져도 422가 아니라 400으로 답하도록 기본값을 빈 문자열로 둔다
class RoomMessageRequest(MessageRequest):
    juniorId: str = ""


class RoomEndRequest(EndRequest):
    juniorId: str = ""


class RoomEndResponseRequest(EndResponseRequest):
    juniorId: str = ""


class RoomReportRequest(ReportRequest):
    juniorId: str = ""


def _require_mentor(mentor_id: str) -> None:
    if not any(mentor.mentor_id == mentor_id for mentor in store.list()):
        raise HTTPException(status_code=404, detail="선배를 찾을 수 없습니다.")


def _chat_room(mentor_id: str, junior_id: str) -> str:
    _require_mentor(mentor_id)
    if not JUNIOR_ID_PATTERN.fullmatch(junior_id):
        raise HTTPException(status_code=400, detail="juniorId 형식이 올바르지 않습니다.")
    return f"{mentor_id}:{junior_id}"


def _bearer(authorization: str) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _require_senior(mentor_id: str, authorization: str) -> None:
    """선배로 하는 요청은 그 선배의 로그인 토큰이 있어야 한다."""
    if storage.token_mentor(_bearer(authorization)) != mentor_id:
        raise HTTPException(status_code=401, detail="선배 로그인이 필요합니다.")


def _require_junior(junior_id: str, authorization: str) -> None:
    """후배로 하는 요청은 그 후배의 로그인 토큰이 있어야 한다(다른 후배의 방이면 401)."""
    if storage.token_junior(_bearer(authorization)) != junior_id:
        raise HTTPException(status_code=401, detail="후배 로그인이 필요합니다.")


def _require_role(role: str, mentor_id: str, junior_id: str, authorization: str) -> None:
    if role == "senior":
        _require_senior(mentor_id, authorization)
    else:
        _require_junior(junior_id, authorization)


def _require_room_member(mentor_id: str, junior_id: str, authorization: str) -> None:
    """대화방을 읽는 요청은 그 방의 선배 또는 후배 토큰이 있어야 한다."""
    token = _bearer(authorization)
    if storage.token_mentor(token) == mentor_id or storage.token_junior(token) == junior_id:
        return
    raise HTTPException(status_code=401, detail="로그인이 필요합니다.")


CHAT_BADWORD_DETAIL = "부적절한 채팅입니다. 바른 표현을 사용해 주세요."
PROFILE_BADWORD_DETAIL = "부적절한 표현이 포함돼 있어요"


def _reject_badwords(detail: str, *texts: str) -> None:
    """금지어가 있으면 400. 어떤 단어가 걸렸는지는 응답에 넣지 않는다."""
    if any(contains_badword(text) for text in texts):
        raise HTTPException(status_code=400, detail=detail)


def _check_new_pin(pin: str, pin_confirm: str) -> None:
    if not PIN_PATTERN.fullmatch(pin):
        raise HTTPException(status_code=400, detail="PIN은 숫자 4~6자리로 입력해 주세요.")
    if pin != pin_confirm:
        raise HTTPException(status_code=400, detail="PIN이 일치하지 않아요.")


def _login(kind: str, display_name: str, pin: str, check) -> str:
    """닉네임·PIN 확인. 같은 닉네임으로 5번 연속 틀리면 5분 잠금."""
    key = (kind, display_name)
    now = time.time()
    with _login_lock:
        fails = _login_fails.get(key)
        if fails and fails["until"] > now:
            raise HTTPException(status_code=429, detail="로그인 시도가 너무 많아요. 5분 후 다시 시도해 주세요.")
    owner_id = check(display_name, pin) if PIN_PATTERN.fullmatch(pin) else None
    with _login_lock:
        if owner_id is None:
            fails = _login_fails.setdefault(key, {"count": 0, "until": 0.0})
            fails["count"] += 1
            if fails["count"] >= LOGIN_MAX_FAILS:
                fails.update(count=0, until=now + LOGIN_LOCK_SECONDS)
                raise HTTPException(status_code=429, detail="5번 틀려서 5분 동안 로그인할 수 없어요.")
            raise HTTPException(status_code=401, detail="닉네임 또는 PIN이 맞지 않아요.")
        _login_fails.pop(key, None)
    return owner_id


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
    if payload.extraction is not None:
        return payload.extraction, "client"

    text = _concern_text(payload.concern_text, payload.choice)
    if not text:
        raise HTTPException(
            status_code=400,
            detail="concern_text 또는 extraction이 필요합니다.",
        )

    if payload.use_llm:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise HTTPException(status_code=503, detail="LLM 설정이 없습니다.")
        raw = extract_concern_info(text)
        if _llm_failed(raw):
            raise HTTPException(status_code=503, detail="LLM 고민 분석에 실패했습니다.")
        return _from_llm(raw), "llm"

    return Extraction(**stub_extract(text)), "stub"


def _rank_mentors(payload: MatchRequest, extraction: Extraction, mentors: list[dict], top_k: int) -> list[dict]:
    return match_mentors(
        interests=extraction.interests,
        help_fields=extraction.help_fields,
        situation=extraction.situation,
        choice_reason=payload.choice.reason if payload.choice else "",
        experience_preferences=payload.choice.experience_preferences if payload.choice else [],
        choice_status=payload.choice.status if payload.choice else "",
        mentors=mentors,
        top_k=top_k,
    )


def _apply_llm_ranking(ranked: list[dict], analysis: dict, top_k: int) -> list[dict]:
    suitability = {
        item["mentor_id"]: item
        for item in analysis.get("suitability", [])
        if isinstance(item, dict) and item.get("mentor_id")
    }
    ranked_by_id = {str(row["mentor_id"]): row for row in ranked}
    reordered: list[dict] = []
    selected_ids: set[str] = set()

    def take(mentor_id: str, reason: str) -> None:
        row = ranked_by_id.get(mentor_id)
        if row is None or mentor_id in selected_ids:
            return
        copied = row.copy()
        fit = suitability.get(mentor_id, {}).get("fit")
        if isinstance(fit, (int, float)):
            copied["score"] = fit
        copied["reasons"] = [reason]
        reordered.append(copied)
        selected_ids.add(mentor_id)

    for item in analysis.get("recommendations", []):
        if len(reordered) >= top_k:
            break
        take(str(item.get("mentor_id") or ""), str(item.get("reason") or "").strip())

    leftovers: list[dict] = []
    for row in ranked:
        mentor_id = str(row["mentor_id"])
        if mentor_id in selected_ids:
            continue
        copied = row.copy()
        extra = suitability.get(mentor_id)
        if extra:
            copied["score"] = extra.get("fit", copied["score"])
            if extra.get("reason"):
                copied["reasons"] = [str(extra["reason"])]
        leftovers.append(copied)
    leftovers.sort(key=lambda item: item["score"], reverse=True)
    reordered.extend(leftovers)
    return reordered[:top_k]


def _match_response(payload: MatchRequest) -> MatchResponse:
    mentors = store.as_matching_rows()
    mentor_source = store.source_path.name if store.source_path else ""
    text = _concern_text(payload.concern_text, payload.choice)

    if payload.use_llm:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise HTTPException(status_code=503, detail="LLM 설정이 없습니다.")
        if payload.extraction is None and not text:
            raise HTTPException(
                status_code=400,
                detail="concern_text 또는 extraction이 필요합니다.",
            )
        seed = payload.extraction or Extraction(**stub_extract(text))
        shortlist_size = max(payload.top_k, min(8, len(mentors)))
        shortlist = _rank_mentors(payload, seed, mentors, shortlist_size)
        if not shortlist:
            return MatchResponse(
                extraction=seed,
                matches=[],
                extraction_source="client" if payload.extraction is not None else "stub",
                recommendation_source="rules",
                mentor_source=mentor_source,
            )
        analysis = analyze_and_recommend(
            concern_text=text or seed.situation,
            candidates=shortlist,
            top_k=payload.top_k,
        )
        if not analysis or not analysis.get("recommendations"):
            raise HTTPException(status_code=503, detail="LLM 고민 분석에 실패했습니다.")
        extraction = payload.extraction or _from_llm(analysis)
        ranked = _apply_llm_ranking(shortlist, analysis, payload.top_k)
        return MatchResponse(
            extraction=extraction,
            matches=[MentorMatch(**row) for row in ranked],
            extraction_source="client" if payload.extraction is not None else "llm",
            recommendation_source="llm",
            mentor_source=mentor_source,
        )

    extraction, source = _extract(payload)
    ranked = _rank_mentors(payload, extraction, mentors, payload.top_k)
    return MatchResponse(
        extraction=extraction,
        matches=[MentorMatch(**row) for row in ranked],
        extraction_source=source,
        recommendation_source="rules",
        mentor_source=mentor_source,
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/frontend/main.html")


@app.get("/api/mentors", response_model=list[MentorOut])
def get_mentors():
    return [MentorOut(**mentor.to_dict()) for mentor in store.list()]


class MentorRegisterRequest(BaseModel):
    display_name: str = ""
    major: str = ""
    status: str = ""
    introduction: str = ""
    pin: str = ""
    pin_confirm: str = ""


class MentorLoginRequest(BaseModel):
    display_name: str = ""
    pin: str = ""


class JuniorRegisterRequest(BaseModel):
    display_name: str = ""
    pin: str = ""
    pin_confirm: str = ""


@app.post("/api/mentors/register")
def register_mentor(payload: MentorRegisterRequest):
    display_name = payload.display_name.strip()
    major = payload.major.strip()
    status = payload.status.strip()
    introduction = payload.introduction.strip()
    if not all((display_name, major, status, introduction)):
        raise HTTPException(status_code=400, detail="닉네임, 전공, 학년, 소개를 모두 입력해 주세요.")
    if len(display_name) > 30:
        raise HTTPException(status_code=400, detail="닉네임은 30자 이내로 입력해 주세요.")
    if len(introduction) > 300:
        raise HTTPException(status_code=400, detail="소개는 300자 이내로 입력해 주세요.")
    _check_new_pin(payload.pin, payload.pin_confirm)
    _reject_badwords(PROFILE_BADWORD_DETAIL, display_name, introduction)
    with _register_lock:
        if storage.name_taken(display_name) or any(
            mentor.display_name == display_name for mentor in store.list()
        ):
            raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임이에요.")
        mentor = store.add(display_name, major, status, introduction)
        try:
            storage.add_mentor(mentor.mentor_id, display_name, major, status, introduction, payload.pin)
        except sqlite3.Error:
            store._mentors.remove(mentor)
            raise
    token = storage.create_token(mentor.mentor_id)
    return {"mentor_id": mentor.mentor_id, "display_name": mentor.display_name, "token": token}


@app.post("/api/mentors/login")
def login_mentor(payload: MentorLoginRequest):
    mentor_id = _login("senior", payload.display_name.strip(), payload.pin, storage.check_pin)
    return {"mentor_id": mentor_id, "token": storage.create_token(mentor_id)}


@app.post("/api/juniors/register")
def register_junior(payload: JuniorRegisterRequest):
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="닉네임을 입력해 주세요.")
    if len(display_name) > 30:
        raise HTTPException(status_code=400, detail="닉네임은 30자 이내로 입력해 주세요.")
    _check_new_pin(payload.pin, payload.pin_confirm)
    _reject_badwords(PROFILE_BADWORD_DETAIL, display_name)
    try:
        junior_id = storage.add_junior(display_name, payload.pin)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임이에요.") from exc
    token = storage.create_junior_token(junior_id)
    return {"junior_id": junior_id, "display_name": display_name, "token": token}


@app.post("/api/juniors/login")
def login_junior(payload: MentorLoginRequest):
    display_name = payload.display_name.strip()
    junior_id = _login("junior", display_name, payload.pin, storage.check_junior_pin)
    return {"junior_id": junior_id, "display_name": display_name, "token": storage.create_junior_token(junior_id)}


@app.get("/api/juniors/me")
def current_junior(authorization: str = Header(default="")):
    junior_id = storage.token_junior(_bearer(authorization))
    if junior_id is None:
        raise HTTPException(status_code=401, detail="후배 로그인이 필요합니다.")
    return {"junior_id": junior_id, "display_name": storage.junior_names([junior_id]).get(junior_id, "")}


@app.post("/api/juniors/logout")
def logout_junior(authorization: str = Header(default="")):
    token = _bearer(authorization)
    if token:
        storage.delete_junior_token(token)
    return {"status": "ok"}


@app.get("/api/mentors/me")
def current_mentor(authorization: str = Header(default="")):
    mentor_id = storage.token_mentor(_bearer(authorization))
    mentor = next((m for m in store.list() if m.mentor_id == mentor_id), None) if mentor_id else None
    if mentor is None:
        raise HTTPException(status_code=401, detail="선배 로그인이 필요합니다.")
    return {"mentor_id": mentor.mentor_id, "display_name": mentor.display_name}


@app.post("/api/mentors/logout")
def logout_mentor(authorization: str = Header(default="")):
    token = _bearer(authorization)
    if token:
        storage.delete_token(token)
    return {"status": "ok"}


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
    _restore_registered()
    count = len(store.list())
    return {"count": count, "mentor_source": store.source_path.name if store.source_path else ""}


@app.post("/api/extract", response_model=Extraction)
def extract_concern(payload: MatchRequest):
    extraction, _source = _extract(payload)
    return extraction


@app.post("/api/match", response_model=MatchResponse)
def match_mentor(payload: MatchRequest):
    return _match_response(payload)


@app.get("/api/messages")
def get_messages(mentorId: str, juniorId: str = "", authorization: str = Header(default="")):
    room = _chat_room(mentorId, juniorId)
    _require_room_member(mentorId, juniorId, authorization)
    return storage.list_messages(room)


# ---- 관리자 (신고 확인에만 비밀번호 필요) ----
ADMIN_TOKEN_SECONDS = 12 * 60 * 60
_admin_tokens: dict[str, float] = {}  # 토큰 해시 → 만료 시각
_admin_fails = {"count": 0, "until": 0.0}
_admin_lock = threading.Lock()


class AdminLoginRequest(BaseModel):
    password: str = ""


def _admin_password() -> str:
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not password:
        raise HTTPException(status_code=503, detail="관리자 비밀번호가 설정되지 않았습니다.")
    return password


def _require_admin(authorization: str) -> None:
    _admin_password()
    token_hash = hashlib.sha256(_bearer(authorization).encode()).hexdigest()
    with _admin_lock:
        expires = _admin_tokens.get(token_hash)
        if expires is None or expires < time.time():
            _admin_tokens.pop(token_hash, None)
            raise HTTPException(status_code=401, detail="관리자 로그인이 필요합니다.")


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    password = _admin_password()
    now = time.time()
    with _admin_lock:
        if _admin_fails["until"] > now:
            raise HTTPException(status_code=429, detail="로그인 시도가 너무 많아요. 5분 후 다시 시도해 주세요.")
        if not secrets.compare_digest(payload.password.encode(), password.encode()):
            _admin_fails["count"] += 1
            if _admin_fails["count"] >= LOGIN_MAX_FAILS:
                _admin_fails.update(count=0, until=now + LOGIN_LOCK_SECONDS)
                raise HTTPException(status_code=429, detail="5번 틀려서 5분 동안 로그인할 수 없어요.")
            raise HTTPException(status_code=401, detail="비밀번호가 맞지 않아요.")
        _admin_fails["count"] = 0
        token = secrets.token_urlsafe(32)
        _admin_tokens[hashlib.sha256(token.encode()).hexdigest()] = now + ADMIN_TOKEN_SECONDS
    return {"token": token, "expiresIn": ADMIN_TOKEN_SECONDS}


def _find_report(report_id: str) -> dict:
    report = storage.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    return report


@app.get("/api/admin/reports")
def get_admin_reports(authorization: str = Header(default="")):
    _require_admin(authorization)
    mentor_names = {mentor.mentor_id: mentor.display_name for mentor in store.list()}
    saved = storage.list_reports()
    junior_names = storage.junior_names([item["juniorId"] for item in saved])
    reports = [
        {
            "reportId": item["reportId"],
            "mentorName": mentor_names.get(item["mentorId"], item["mentorId"]),
            "juniorName": junior_names.get(item["juniorId"], ""),
            "reporterRole": "선배" if item["reporterRole"] == "senior" else "후배",
            "reason": item["reason"],
            "detail": item["details"],
            "createdAt": item["createdAt"],
        }
        for item in saved
    ]
    reports.sort(key=lambda item: datetime.fromisoformat(item["createdAt"]), reverse=True)
    return reports


@app.get("/api/admin/reports/{report_id}/messages")
def get_admin_report_messages(report_id: str, authorization: str = Header(default="")):
    """신고된 대화방의 메시지만 볼 수 있다."""
    _require_admin(authorization)
    report = _find_report(report_id)
    return storage.list_messages(f"{report['mentorId']}:{report['juniorId']}")


@app.get("/api/admin/matches")
def get_admin_matches(authorization: str = Header(default="")):
    """시연용 관리자 화면: 전체 대화방 목록(최근순). 메시지 내용은 넣지 않는다."""
    _require_admin(authorization)
    mentor_names = {mentor.mentor_id: mentor.display_name for mentor in store.list()}
    rooms = storage.list_rooms("")
    junior_ids = [room["room"].partition(":")[2] for room in rooms]
    junior_names = storage.junior_names(junior_ids)
    reported_rooms = {f"{item['mentorId']}:{item['juniorId']}" for item in storage.list_reports()}
    matches = []
    for room, junior_id in zip(rooms, junior_ids):
        mentor_id = room["room"].partition(":")[0]
        first = storage.list_messages(room["room"])[0]  # 첫 메시지 시각만 사용
        matches.append(
            {
                "mentorName": mentor_names.get(mentor_id, ""),
                "mentorId": mentor_id,
                "juniorName": junior_names.get(junior_id, ""),
                "createdAt": first["createdAt"],
                "lastAt": room["lastAt"],
                "messageCount": room["messageCount"],
                "status": room["status"],
                "reported": room["room"] in reported_rooms,
            }
        )
    matches.sort(key=lambda item: datetime.fromisoformat(item["lastAt"]), reverse=True)
    return matches


@app.get("/api/rooms")
def get_rooms(mentorId: str, authorization: str = Header(default="")):
    _require_mentor(mentorId)
    _require_senior(mentorId, authorization)
    prefix = f"{mentorId}:"
    rooms = [
        {
            "juniorId": room.pop("room").removeprefix(prefix),
            **room,
        }
        for room in storage.list_rooms(prefix)
    ]
    names = storage.junior_names([room["juniorId"] for room in rooms])
    for room in rooms:
        room["juniorName"] = names.get(room["juniorId"], "")
    rooms.sort(key=lambda item: datetime.fromisoformat(item["lastAt"]), reverse=True)
    return rooms


@app.post("/api/messages")
def send_message(payload: RoomMessageRequest, authorization: str = Header(default="")):
    room = _chat_room(payload.mentorId, payload.juniorId)
    if payload.senderRole not in {"junior", "senior"}:
        raise HTTPException(status_code=400, detail="senderRole이 올바르지 않습니다.")
    _require_role(payload.senderRole, payload.mentorId, payload.juniorId, authorization)
    if storage.get_end_state(room)["status"] == "ended":
        raise HTTPException(status_code=409, detail="종료된 대화입니다.")
    _reject_badwords(CHAT_BADWORD_DETAIL, payload.text)
    message = {
        "id": str(uuid.uuid4()),
        "senderRole": payload.senderRole,
        "text": payload.text.strip(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    storage.add_message(room, message)
    return message


@app.get("/api/chat-end")
def get_chat_end(mentorId: str, juniorId: str = "", authorization: str = Header(default="")):
    room = _chat_room(mentorId, juniorId)
    _require_room_member(mentorId, juniorId, authorization)
    return storage.get_end_state(room)


@app.post("/api/chat-end/request")
def request_chat_end(payload: RoomEndRequest, authorization: str = Header(default="")):
    room = _chat_room(payload.mentorId, payload.juniorId)
    if payload.requesterRole not in {"junior", "senior"}:
        raise HTTPException(status_code=400, detail="requesterRole이 올바르지 않습니다.")
    _require_role(payload.requesterRole, payload.mentorId, payload.juniorId, authorization)
    state = storage.get_end_state(room)
    if state["status"] != "active":
        return state
    state.update(status="pending", requestedBy=payload.requesterRole, declinedBy=None)
    storage.save_end_state(room, state)
    return state


@app.post("/api/chat-end/respond")
def respond_chat_end(payload: RoomEndResponseRequest, authorization: str = Header(default="")):
    room = _chat_room(payload.mentorId, payload.juniorId)
    _require_role(payload.responderRole, payload.mentorId, payload.juniorId, authorization)
    state = storage.get_end_state(room)
    if state["status"] != "pending":
        return state
    if payload.responderRole == state["requestedBy"]:
        raise HTTPException(status_code=400, detail="요청자는 응답할 수 없습니다.")
    if payload.agree:
        state.update(status="ended", requestedBy=None, declinedBy=None)
    else:
        state.update(status="active", requestedBy=None, declinedBy=payload.responderRole)
    storage.save_end_state(room, state)
    return state


@app.post("/api/reports")
def create_report(payload: RoomReportRequest, authorization: str = Header(default="")):
    _chat_room(payload.mentorId, payload.juniorId)
    _require_role(payload.reporterRole, payload.mentorId, payload.juniorId, authorization)
    _reject_badwords(CHAT_BADWORD_DETAIL, payload.details)
    storage.add_report(
        {
            "reportId": str(uuid.uuid4()),
            "mentorId": payload.mentorId,
            "juniorId": payload.juniorId,
            "reporterRole": payload.reporterRole,
            "reason": payload.reason,
            "details": payload.details,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"status": "received"}


if FRONTEND_DIR.is_dir():
    app.mount(
        "/frontend",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )
