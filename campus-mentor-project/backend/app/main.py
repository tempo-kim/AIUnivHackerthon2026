from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# AI 추출 함수 불러오기
from ai.extractor import extract_concern_info

app = FastAPI()

# 💡 [필수] 프론트엔드 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 프론트엔드가 POST /api/match 로 보낼 데이터 구조 정의
class MatchRequest(BaseModel):
    text: Optional[str] = None       # 후배 고민글 문장
    user_id: Optional[str] = None    # (선택) 유저 ID
    # 프론트엔드에서 추가로 보내는 값이 있다면 여기에 필드를 추가하면 됩니다.

# -------------------------------------------------------------
# [엔드포인트 1] Health Check (프론트: MentorApi.health())
# -------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}

# -------------------------------------------------------------
# [엔드포인트 2] 멘토 목록 조회 (프론트: MentorApi.listMentors())
# -------------------------------------------------------------
@app.get("/api/mentors")
def get_mentors():
    # 해커톤용 가짜(Dummy) 멘토 데이터 목록
    return [
        {
            "id": 1,
            "name": "김선배",
            "major": "컴퓨터공학과",
            "interests": ["데이터 분석", "진로 탐색"],
            "introduction": "데이터 분석 진로 및 공부 방법 상담 환영합니다!"
        },
        {
            "id": 2,
            "name": "이선배",
            "major": "인공지능학과",
            "interests": ["AI", "백엔드"],
            "introduction": "인공지능 모델링 및 백엔드 개발 관련 팁 드립니다."
        }
    ]

# -------------------------------------------------------------
# [엔드포인트 3] AI 매칭 및 조건 추출 (프론트: MentorApi.match(body))
# -------------------------------------------------------------
@app.post("/api/match")
def match_mentor(payload: MatchRequest):
    print("\n========================================")
    print(f"📩 [프론트엔드 수신 데이터]: {payload}")
    print("========================================\n")

    # 1. 프론트엔드가 보내준 고민글 텍스트 추출
    user_text = payload.text or "고민글 내용이 전달되지 않았습니다."

    # 2. 내 AI extractor.py 함수 실행해서 분석 결과 받아오기
    ai_result = extract_concern_info(user_text)

    # 3. 프론트엔드에 AI 결과 + 매칭된 결과 반환
    return {
        "status": "success",
        "extracted_info": ai_result,  # AI가 추출한 interests, situation, help_fields
        "recommended_mentors": [       # 추천 멘토 결과 (가짜 데이터 연결)
            {
                "id": 1,
                "name": "김선배",
                "match_score": 95,
                "reason": "데이터 분석 진로 고민에 최적화된 멘토입니다."
            }
        ]
    }