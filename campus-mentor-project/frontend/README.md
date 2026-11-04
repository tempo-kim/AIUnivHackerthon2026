# 프론트엔드 (매칭까지)

## 화면 흐름

1. `main.html` — 학적/이유/세부 선택 → `sessionStorage.ppunppun-choice`
2. `concern/` — 고민 문장 입력 → `POST /api/match`
3. `result/` — 추천 선배 표시 (`ppunppun-match`)
4. `chat/` — **추후** (지금은 안내만)

## 실행

백엔드와 함께 같은 서버로 여는 것을 권장합니다.

```bash
cd campus-mentor-project/backend
uvicorn app.main:app --reload --port 8000
```

브라우저: http://127.0.0.1:8000/frontend/main.html

로그인/회원가입은 아직 없습니다. 시연은 비로그인으로 진행합니다.
