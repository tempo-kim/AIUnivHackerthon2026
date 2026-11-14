# 뻔뻔하게 — 선배 매칭·채팅 서비스

후배가 학교생활이나 진로 고민을 입력하면 적합한 선배를 추천하고, 로그인한 후배가 선배와 채팅할 수 있는 MVP입니다. 이 문서는 팀원이 LLM 추천, 가입·로그인, DB 저장, 채팅, 다음 추천 API를 빠르게 파악하도록 현재 구현을 정리합니다.

## 프로젝트 구성

| 경로 | 역할 |
| --- | --- |
| `frontend/main.html` | 역할 선택, 후배 가입·로그인, 고민 입력, 추천 요청 |
| `frontend/result/index.html` | 추천 선배, 관심 선배, 다른 선배 요청, 후배 채팅 이력 |
| `frontend/chat/` | 선배·후배 채팅 화면과 API 클라이언트 |
| `frontend/assets/achievements.js` | 계정별 배지 UI, 채팅 이력 기반 배지 동기화 |
| `backend/app/main.py` | FastAPI 라우트, 인증, 매칭 조정, 채팅 API |
| `backend/matching/matcher.py` | 프로필과 고민의 규칙 기반 점수 계산 |
| `backend/ai/extractor.py` | 고민 분석과 후보 적합도·추천 이유 생성 |
| `backend/services/mentors.py` | CSV 및 메모리 내 선배 프로필 관리 |
| `backend/services/storage.py` | SQLite 계정·토큰·메시지·종료 상태 저장 |
| `data/` | 기본 선배 프로필 CSV와 서비스 샘플 데이터 |

## 실행

Python 가상 환경을 만든 뒤 백엔드 의존성을 설치하고 프로젝트 루트가 아닌 `backend` 디렉터리에서 실행합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

브라우저에서 `http://127.0.0.1:8000/frontend/main.html`을 엽니다. 헬스 확인은 `GET /health`입니다. LLM 연동은 서버 환경변수 설정이 필요하며, 키나 비밀번호를 소스 코드·프론트엔드·README에 기록하거나 커밋하지 마세요.

## LLM 추천 흐름

1. 화면은 선택한 학적·도움 분야·경험 선호와 자유 입력 고민을 `POST /api/match`로 보냅니다. 기본 요청은 `use_llm: true`, `top_k: 3`입니다.
2. 백엔드는 전체 선배 프로필을 `matching/matcher.py`로 먼저 정렬해 LLM에 전달할 후보군을 줄입니다. 후보에는 CSV 선배와 서버에 가입해 등록된 선배가 모두 들어갑니다.
3. `analyze_and_recommend`가 고민의 핵심 관심사·상황·도움 분야를 뽑고, 후보 프로필에 대한 적합도와 추천 이유 및 순위를 만듭니다. 반환된 선배 ID는 전달된 후보에 존재하는 ID로 검증합니다.
4. LLM 결과가 없거나 형식이 올바르지 않으면 규칙 기반 순위로 응답합니다. 응답의 `extraction_source`와 `recommendation_source`를 보면 실제 사용 경로를 알 수 있습니다.

요청 예시:

```json
{
  "concern_text": "컴퓨터공학과 2학년인데 인턴 준비를 어디서 시작할지 궁금해요.",
  "choice": {
    "status": "재학생",
    "reason": "진로와 취업",
    "experience_preferences": ["인턴 경험", "비슷한 전공"]
  },
  "top_k": 3,
  "use_llm": true
}
```

응답은 `extraction`, `matches`, `extraction_source`, `recommendation_source`, `mentor_source`를 포함합니다. 각 `matches` 항목에는 `mentor_id`, `display_name`, `major`, `experiences`, `help_topics`, `bio`, `score`, `reasons`가 있습니다.

| 응답 필드 | 예시 의미 |
| --- | --- |
| `extraction_source` | `llm`, `stub`, `client` 등 분석 입력의 출처 |
| `recommendation_source` | `llm`, `rules`, `rules-fallback` 등 순위 결정 경로 |
| `mentor_source` | 기본 후보 CSV 등 현재 프로필 원본 |

## 다음 3명 추천 API

결과 화면의 `다른 선배 보기`는 이미 보여준 선배 ID를 제외하고 다음 후보를 요청합니다. 현재 프론트엔드는 첫 추천 결과와 이후 페이지의 ID를 `sessionStorage`에 모아 다시 보냅니다.

```http
POST /api/match
Content-Type: application/json
```

```json
{
  "concern_text": "이전과 같은 고민 문장",
  "choice": { "status": "재학생", "reason": "진로와 취업" },
  "extraction": {
    "interests": ["인턴"],
    "situation": "인턴 준비를 시작하려는 재학생",
    "help_fields": ["진로취업"]
  },
  "top_k": 3,
  "rank_offset": 0,
  "exclude_mentor_ids": ["M001", "M014", "M023"],
  "use_llm": false
}
```

다음 페이지는 규칙 점수로 전체 후보를 다시 정렬하고 `exclude_mentor_ids`에 있는 프로필을 빼고 최대 3명을 돌려줍니다. 후보가 3명보다 적으면 있는 만큼만 반환하며 더 이상 후보가 없으면 `matches`는 빈 배열입니다. 매칭 요청은 로그인 토큰이 필요하지 않습니다.

## 가입·로그인과 DB

### 가입·로그인 API

| 기능 | API | 성공 응답의 주요 필드 |
| --- | --- | --- |
| 후배 가입 | `POST /api/juniors/register` | `junior_id`, `display_name`, `token` |
| 후배 로그인 | `POST /api/juniors/login` | `junior_id`, `display_name`, `token` |
| 선배 가입·프로필 등록 | `POST /api/mentors/register` | `mentor_id`, `display_name`, `token` |
| 선배 로그인 | `POST /api/mentors/login` | `mentor_id`, `token` |
| 현재 사용자 확인 | `GET /api/juniors/me`, `GET /api/mentors/me` | ID와 닉네임 |
| 로그아웃 | `POST /api/juniors/logout`, `POST /api/mentors/logout` | `{ "status": "ok" }` |

가입 요청은 역할별 닉네임, 숫자 PIN, PIN 확인을 받습니다. 선배 가입에는 전공, 학적 상태, 소개도 필요합니다. PIN은 4~6자리 숫자이며 DB에는 솔트와 PBKDF2 해시만 저장합니다. 로그인 응답의 토큰은 브라우저에서 저장하고, 보호된 API에는 `Authorization: Bearer <token>` 헤더로 전달합니다. DB에는 토큰 원문 대신 SHA-256 해시를 저장하고 토큰은 30일 후 만료됩니다. 같은 닉네임으로 로그인에 5회 연속 실패하면 5분간 잠깁니다.

### 저장 위치

| 데이터 | 저장 방식 |
| --- | --- |
| 기본 선배 프로필 | `data/Mentors.csv`, `data/220.new.mentors.csv`를 서버 시작 시 읽어 메모리 후보로 로드 |
| 서비스에서 가입한 선배 프로필 | SQLite `mentors` 테이블에 저장하고, 가입 즉시 메모리 매칭 목록에도 반영 |
| 후배 계정 | SQLite `juniors` 테이블 |
| 선배·후배 로그인 토큰 해시 | SQLite `tokens`, `junior_tokens` 테이블 |
| 채팅 메시지 | SQLite `messages` 테이블 |
| 대화 종료 상태 | SQLite `end_states` 테이블 |
| 신고 | SQLite `reports` 테이블 |

SQLite 파일 경로는 `backend/data/app.db`입니다. 배포 환경에서는 재시작 후에도 파일이 남도록 영속 디스크를 설정해야 계정과 채팅 기록을 보존할 수 있습니다. 기본 CSV를 바꾸거나 다시 읽는 관리 API는 `POST /api/mentors/import`, `POST /api/mentors/reload`입니다.

## 채팅 API와 대화방

대화방 키는 서버에서 `<mentor_id>:<junior_id>` 형식으로 만듭니다. 메시지 읽기·쓰기와 종료 상태 조회는 해당 방의 선배 또는 후배 로그인 토큰이 있어야 합니다.

| 기능 | API | 비고 |
| --- | --- | --- |
| 메시지 전송 | `POST /api/messages` | JSON에 `mentorId`, `juniorId`, `senderRole`, `text` 전달 |
| 메시지 이력 | `GET /api/messages?mentorId=...&juniorId=...` | 방 멤버만 읽을 수 있음 |
| 선배의 받은 대화 | `GET /api/rooms?mentorId=...` | 해당 선배 로그인 필요 |
| 후배의 채팅 기록 목록 | `GET /api/junior-rooms` | 후배 Bearer 토큰 필요 |
| 대화 종료 상태 | `GET /api/chat-end?...` | `active`, `pending`, `ended` |
| 종료 요청 | `POST /api/chat-end/request` | 실제 계정 선배는 상대가 동의·거절 |
| 종료 응답 | `POST /api/chat-end/respond` | `agree: true/false` |
| 후배 업적 기록 조회 | `GET /api/junior-achievements` | 채팅 이력으로 첫걸음·인연 탐험가 계산 |

메시지 요청 예시:

```json
{
  "mentorId": "M001",
  "juniorId": "J-Ab12Cd34",
  "senderRole": "junior",
  "text": "인턴 준비는 언제부터 시작하셨어요?"
}
```

브라우저의 서버 모드 채팅은 약 3초 간격으로 메시지와 종료 상태를 조회합니다. `GET /api/junior-rooms`는 마지막 메시지, 시각, 메시지 수, 종료 상태와 선배 이름을 반환해 기록 화면을 구성합니다. 데이터 기반 프로필에 선배 로그인 계정이 없으면 후배의 종료 요청을 자동 동의 처리합니다. 가입 계정이 있는 선배는 일반 종료 요청 절차를 사용합니다.

## 핵심 API 목록

| Method | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/health` | 없음 | 서버 상태 |
| `GET` | `/api/mentors` | 없음 | 추천에 사용되는 전체 선배 프로필 |
| `POST` | `/api/match` | 없음 | 추천·다음 후보 요청 |
| `POST` | `/api/juniors/register` | 없음 | 후배 가입 |
| `POST` | `/api/juniors/login` | 없음 | 후배 로그인 |
| `POST` | `/api/mentors/register` | 없음 | 선배 가입 및 프로필 등록 |
| `POST` | `/api/mentors/login` | 없음 | 선배 로그인 |
| `GET` | `/api/messages` | 방 멤버 | 채팅 이력 |
| `POST` | `/api/messages` | 발신 사용자 | 메시지 저장 |
| `GET` | `/api/rooms` | 해당 선배 | 받은 대화 목록 |
| `GET` | `/api/junior-rooms` | 해당 후배 | 내 채팅 기록 목록 |

전체 입력·응답 스키마는 실행 중인 FastAPI의 `/docs`에서도 확인할 수 있습니다.
