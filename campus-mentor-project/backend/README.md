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

## LLM

`.env`에 `OPENAI_API_KEY` (+ OpenRouter면 `OPENAI_BASE_URL`)가 있으면 추출에 LLM을 씁니다.  
없으면 키워드 stub으로 데모 가능합니다.
