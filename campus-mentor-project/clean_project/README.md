# 캠퍼스 선배 매칭 MVP (뻔뻔하게)

후배가 고민을 입력하면 LLM이 분석하고, Syntitan으로 정리된 선배 데이터와 매칭합니다.  
**채팅은 다음 단계**에서 연결합니다.

## 폴더

```text
frontend/     시작 → 고민 입력 → 매칭 결과 (chat은 추후)
backend/      FastAPI + LLM 추출 + 매칭
data/         mentors.cleaned.csv (Syntitan 정리본), raw/
```

## 빠른 실행

```bash
cd campus-mentor-project/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

http://127.0.0.1:8000/frontend/main.html

## 브랜치

백엔드·프론트 통합 작업: `back/match-api`  
PR로 `main`에 합칩니다. API 키는 `.env`에만 두고 커밋하지 않습니다.
