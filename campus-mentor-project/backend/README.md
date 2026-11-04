# Backend

| 경로 | 역할 |
|------|------|
| `app/` | FastAPI 서버 (`/health`, `/api/match`) |
| `matching/` | 선배 CSV 규칙 매칭 |
| `ai/stub_extract.py` | 키 없이 쓰는 임시 추출 (데모용) |
| `examples/` | 프론트 연동용 요청·응답 JSON 예시 |
| `scripts/smoke_match.ps1` | 로컬 스모크 테스트 |

실제 LLM 추출기(`extractor.py`)는 `AI/extraction` 브랜치에서 작업 중입니다. 이 브랜치는 그 파일을 덮어쓰지 않습니다.

프론트엔드 파일은 수정하지 않습니다.

## 프론트 연동 요약

- Base URL (로컬): `http://127.0.0.1:8000`
- `POST /api/match`
  - body A: `{ "concern_text": "...", "top_k": 3 }`
  - body B: `{ "extraction": { "interests": [], "situation": "", "help_fields": [] }, "top_k": 3 }`
- 응답: `extraction`, `matches[]`(`mentor_id`, `score`, `reasons`, ...), `extraction_source`(`stub`|`llm`|`client`)
- 예시 파일: `examples/match.request.json`, `examples/match.response.example.json`
