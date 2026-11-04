from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# 같은 ai 폴더 안의 extractor.py에서 extract_concern_info 함수를 불러옵니다.
from .extractor import extract_concern_info

app = FastAPI(title="Campus Mentor AI API")

# 1. 프론트엔드에서 보낼 요청 데이터 구조 정의
class ConcernRequest(BaseModel):
    user_text: str

# 2. 서버 작동 확인용 기본 헬스체크 엔드포인트
@app.get("/")
def read_root():
    return {"message": "Campus Mentor AI Server is running!"}

# 3. 프론트엔드가 고민글을 보낼 때 AI 추출 결과를 반환하는 API 엔드포인트
@app.post("/api/extract-concern")
def extract_concern(request: ConcernRequest):
    # 입력값 검증 (공백 처리)
    if not request.user_text.strip():
        raise HTTPException(status_code=400, detail="고민글 내용을 입력해주세요.")
    
    # extractor.py의 AI 추출 함수 호출
    result = extract_concern_info(request.user_text)
    return result