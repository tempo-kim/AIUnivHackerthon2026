# Backend 개발 가이드

전체 기능 설명과 가입·DB·채팅·추천 API 예시는 [프로젝트 README](../README.md)를 참고하세요.

## 개발 서버

프로젝트 루트에서 다음 순서로 실행합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- 헬스 확인: `GET /health`
- API 스키마: `http://127.0.0.1:8000/docs`
- 프론트엔드: `http://127.0.0.1:8000/frontend/main.html`
- SQLite: `backend/data/app.db`

LLM 설정은 서버 프로세스의 환경변수로 주입합니다. 민감한 값은 소스, 프론트엔드, 문서, 커밋에 넣지 않습니다. LLM 요청이 실패하면 매칭은 규칙 기반 결과를 반환할 수 있으므로 응답의 `extraction_source`와 `recommendation_source`를 확인하세요.


## 코드 흐름

1. `app/main.py`가 서버 시작 시 `storage.init()`을 호출하고, CSV 기본 프로필과 SQLite에 저장된 가입 선배 프로필을 매칭 저장소에 올립니다.
2. `/api/match`는 규칙 매처로 후보를 좁힌 뒤 LLM 추천을 요청하거나 규칙 기반 순위를 반환합니다.
3. `services/storage.py`가 계정·토큰·채팅 기록·대화 종료 상태를 SQLite에 읽고 씁니다.
4. 프론트엔드 채팅 API는 서버 모드에서 메시지와 종료 상태를 주기적으로 다시 읽습니다.

## 추천 API 메모

`POST /api/match`는 `top_k`, `use_llm`, `choice`, `extraction`을 선택적으로 받습니다. 이후 후보 요청에는 `exclude_mentor_ids`를 전달해 이미 보여준 선배를 제외할 수 있습니다. `rank_offset`은 규칙 기반 전체 순위에서 페이지를 자를 때 사용합니다. 자세한 JSON 예시와 응답 필드는 루트 README의 **LLM 추천 흐름**과 **다음 3명 추천 API** 절을 참고하세요.

## 배포

저장소 루트의 `render.yaml`이 서비스 구성을 정의합니다. 배포 시 LLM 관련 민감한 환경변수는 호스팅 서비스의 secret/environment 설정에서 관리하고, SQLite 파일을 보존하려면 영속 디스크를 연결해야 합니다. 설정값이나 키를 README에 붙여 넣지 마세요.

## 학교 챗봇

- `POST /api/school-bot` — 학교 관련 질문에 답함 (요청에 `school` 포함 시 해당 학교만 조회)
- 지식 원천:
  - `data/school_bot_facts.json` — 교통·캠퍼스·실존 맛집·공식 AI 전공 사실 카드
  - `data/school_bot_seed_chats.json` — 6교 × 200채팅 × ≥30메시지
  - 실제 DB 익명 채팅
- 사실 카드 + 관련 채팅을 함께 검색(하이브리드). 키 없으면 사실 카드 추출 답변
- 매칭과 **같은** `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `LLM_MODEL` 사용
- 화면: `/frontend/school-bot/` (대기 중 `데이터베이스 조회중입니다` 표시)
