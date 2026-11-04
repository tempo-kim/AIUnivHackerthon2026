# Backend

| 경로 | 역할 |
|------|------|
| `app/` | FastAPI 서버 (`/health`, `/api/match`) |
| `matching/` | 선배 CSV 규칙 매칭 |
| `ai/stub_extract.py` | 키 없이 쓰는 임시 추출 (데모용) |

실제 LLM 추출기(`extractor.py`)는 `AI/extraction` 브랜치에서 작업 중입니다. 이 브랜치는 그 파일을 덮어쓰지 않습니다.

프론트엔드 파일은 수정하지 않습니다.
