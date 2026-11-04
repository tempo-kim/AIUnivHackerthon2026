# 매칭 기능

AI가 추출한 조건과 가상 선배 프로필을 비교하고, 추천 후보와 실제 프로필에 근거한 추천 이유를 반환합니다. 적합한 후보가 없을 때의 동작도 구현합니다.

## 실행 (이 브랜치)

```bash
cd campus-mentor-project/backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- 헬스체크: `GET http://127.0.0.1:8000/health`
- 매칭: `POST http://127.0.0.1:8000/api/match`

```json
{
  "concern_text": "경영학과인데 수강신청이랑 시간표가 막막해요"
}
```

또는 AI 팀이 이미 뽑은 조건을 직접 넣을 수 있습니다.

```json
{
  "extraction": {
    "interests": ["경영학과"],
    "situation": "수강신청 전",
    "help_fields": ["수강신청", "시간표"]
  }
}
```

API 키가 없으면 규칙 기반 stub 추출을 쓰고, `.env`에 OpenRouter 키가 있으면 LLM 추출을 시도합니다.
