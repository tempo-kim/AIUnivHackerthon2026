# 프론트엔드

## 화면

| 경로 | 설명 |
|------|------|
| `main.html` | 팀 플로우: 학적·이용 이유·수업·선배 유형(1~5점) 선택 후 `/api/match` |
| `concern/` | 고민 문장 입력 → LLM/stub 분석 → 매칭 (백엔드 매칭 플로우) |
| `result/` | 매칭 결과 표시 |
| `chat/` | 대화 프로토타입 |

하단 내비에서 **고민 입력**으로 들어가면 문장 기반 매칭을 쓸 수 있습니다.

## 실행

```bash
cd campus-mentor-project/backend
uvicorn app.main:app --reload --port 8000
```

http://127.0.0.1:8000/frontend/main.html
