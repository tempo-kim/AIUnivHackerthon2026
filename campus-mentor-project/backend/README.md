# Backend — 매칭까지 (채팅 제외)

## 역할

| 단계 | 백엔드 |
|------|--------|
| 선배 데이터 | Syntitan 정리본 CSV 로드 (`/api/mentors`, import/reload) |
| 고민 분석 | LLM 추출 (`extractor.py`), 키 없으면 stub |
| 매칭 | 규칙 점수 (`matching/matcher.py`) → top_k |
| 채팅 | 추후 |

## 실행

```bash
cd campus-mentor-project/backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # OpenRouter 키 있으면 입력
uvicorn app.main:app --reload --port 8000
```

- 헬스: `GET /health`
- 선배 목록: `GET /api/mentors`
- 매칭: `POST /api/match`
- Syntitan CSV 반영: `POST /api/mentors/import` `{ "csv_text": "..." }`
- 프론트: http://127.0.0.1:8000/frontend/main.html

## Render 배포

저장소 루트의 `render.yaml`로 Web Service를 생성합니다.

1. Render에서 New > Blueprint를 선택하고 저장소를 연결합니다.
2. `OPENAI_API_KEY`는 Render 환경변수에 직접 입력합니다. 저장소 파일이나 프론트엔드에 입력하지 않습니다.
3. OpenRouter를 사용하는 경우 `OPENAI_BASE_URL`도 Render 환경변수에 직접 입력합니다.
4. 배포가 완료되면 생성된 Render URL 뒤에 `/frontend/main.html`을 붙여 접속합니다.

Render의 `sync: false` 환경변수는 실제 값이 저장소에 기록되지 않도록 비워 둔 설정입니다. 공개 배포 후에는 `FRONTEND_ORIGIN`에 생성된 Render 기본 URL을 입력할 수 있습니다. API 키가 노출되었거나 커밋된 적이 있다면 즉시 폐기하고 새 키를 발급하세요.

## LLM

`.env`에 `OPENAI_API_KEY` (+ OpenRouter면 `OPENAI_BASE_URL`)가 있으면 추출에 LLM을 씁니다.  
없으면 키워드 stub으로 데모 가능합니다.

## 학교 챗봇

- `POST /api/school-bot` — 선배·후배 채팅을 익명으로 모아 학교 관련 질문에 답함
- 매칭과 같은 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `LLM_MODEL` 사용
- 선택한 학교의 관련 대화가 있으면 그 내용을 근거로 답하고, 없으면 학교별 사실을 지어내지 않는 일반 LLM 답변으로 전환함
- 저장 대화가 없을 때는 공개 웹 검색 결과를 보조 근거로 전달하며, 검색 결과가 없으면 일반 답변임을 표시함
- 화면: `/frontend/school-bot/`

