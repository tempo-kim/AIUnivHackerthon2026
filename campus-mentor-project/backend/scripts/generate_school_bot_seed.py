"""시연용 선후배 '긴 채팅' 200개 생성.

각 채팅은 한 주제 안에서 최소 30개 메시지(선·후배 왕복)로 이어진다.
주제: 서울대 주변 맛집 / 인공지능학과 전공.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "school_bot_seed_chats.json"
MIN_MESSAGES = 30
NUM_CHATS = 200  # 맛집 100 + 전공 100
RNG = random.Random(42)


FOOD_PLACES = [
    ("담소소사골순대국", "녹두거리", "수육백반", "9천 원대", "점심 12시 전후 웨이팅"),
    ("파스타리", "샤로수길", "알리오올리오", "1.2만 원대", "대기 20분 안쪽"),
    ("미나리", "샤로수길", "코스요리", "예약 필수", "주말 저녁 만석"),
    ("원조쌈밥", "봉천동", "정식", "8천 원대", "반찬 리필"),
    ("카페온더플랜", "샤로수길 2층", "아메리카노", "콘센트 많음", "비 오는 날 창가 습기"),
    ("정식당", "정문 골목", "한식 정식", "가깝지만 웨이팅", "급하면 김밥천국"),
    ("담백한 국수집", "낙성대 2번 출구", "잔치국수", "순한 맛", "온면 추천"),
    ("카페 느티", "경영대 가는 길", "라떼", "사람 적음", "테이블 간격 좁음"),
    ("뼈해장국24시", "서울대입구", "뼈해장국", "밤 11시 이후", "곱창전골은 양이 큼"),
    ("즉석떡볶이", "녹두", "밀떡 떡볶이", "맵기 2단계", "치즈 추가 시 단맛↑"),
    ("동태탕집", "관악로", "동태탕", "2인 기본", "고수는 따로"),
    ("화덕피자", "샤로수길", "마르게리타", "배달피자보다 나음", "평일 3시 한산"),
    ("순살치킨집", "낙성대", "순살세트", "야식 2만 원 예산", "리뷰 진실한 편"),
    ("연어덮밥집", "샤로수길", "연어덮밥", "밥 양 조절 가능", "헬스 직후 인기"),
    ("한정식집", "역 근처", "정식 코스", "테이블석 예약", "주말 점심이 덜 붐빔"),
]

FOOD_FOLLOWUPS = [
    ("줄은 보통 얼마나 기다려요?", "피크만 피하면 {wait}. 평일 오후는 거의 바로 들어가요."),
    ("가격이 부담되면 대안이 있을까요?", "같은 골목에서 {alt} 쪽이 더 싸고, 맛 차이는 크지 않아요."),
    ("혼자 가도 눈치 안 보여요?", "바 좌석이나 1인석 있는 집이면 괜찮아요. {place}도 혼밥 많아요."),
    ("카드랑 영수증 돼요?", "카드 되고, 영수증은 말할 때 같이 달라고 하면 바로 줍니다."),
    ("포장해서 도서관 가도 돼요?", "국물 메뉴는 냄새·유출 때문에 비추천이에요. 김밥·샌드위치가 안전해요."),
    ("비 오는 날은 어때요?", "입구 바닥이 미끄러우니 큰길로만 다니고, 창가보다 안쪽 자리가 낫습니다."),
    ("예약은 필수예요?", "{place}는 {reserve}. 전화보다 네이버/현장 대기인 집도 있어요."),
    ("몇 명이 가기 좋아요?", "2~3인이 제일 무난하고, 6명 이상이면 방 있는 집으로 미리 연락하세요."),
    ("맵기는 조절돼요?", "요청하면 순한맛으로 바꿔 주는 편이에요. 처음엔 기본보다 한 단계 낮추세요."),
    ("근처에 카페도 이어서 갈까요?", "밥 먹고 {area} 쪽으로 5분만 걸으면 디저트·커피 이어가기 좋아요."),
    ("시험기간에도 사람 많아요?", "시험기간엔 늦은 저녁이 오히려 덜 붐빌 때가 있어요. 점심은 여전히 붐벼요."),
    ("배달도 돼요?", "배민에 '{area}'로 검색해 보세요. 기숙사는 픽업 지정되는 가게가 있어요."),
    ("알레르기 있으면요?", "주문 전에 꼭 말하세요. 소스에 견과·새우 들어가는 집이 있습니다."),
    ("부모님 모시고 가기 괜찮아요?", "좌식인지 테이블석인지 먼저 확인하고, 조용한 시간대(평일 점심)를 고르세요."),
    ("양이 부족한 편이에요?", "{menu} 기준으로는 보통이고, 밥/면 추가가 가능하면 추가하세요."),
]


AI_COURSES = [
    ("인공지능개론", "개념 양 많음", "주 3회 짧은 복습", "자료구조와 동시수강 주의"),
    ("머신러닝", "과제 재현성", "시드 고정·실험노트", "채점 스크립트 로컬 검증"),
    ("딥러닝", "GPU 필요", "작은 모델로 파이프라인 검증", "배치 사이즈부터 축소"),
    ("선형대수", "기하적 이해", "고유값·투영·최소자승", "그림으로 설명 연습"),
    ("확률통계", "조건부확률·기댓값", "손실함수 기댓값 연결", "짧은 인강+문제세트"),
    ("NLP기초", "전처리·임베딩", "TF-IDF→로지스틱→파인튜닝", "API만 쓰면 얕아 보임"),
    ("컴퓨터비전", "메모리 이슈", "해상도·배치 축소", "DataLoader 설정 점검"),
    ("강화학습", "MDP·벨만", "그리드월드부터", "논문부터 가면 길을 잃음"),
    ("AI수학", "추상 정의", "모델과 연결해 메모", "경사하강·행렬미분"),
    ("데이터윤리", "편향 분석", "그룹별 오류 표", "완화책으로 서술"),
]

AI_FOLLOWUPS = [
    ("그럼 이번 주엔 구체적으로 뭘 하면 좋아요?", "이번 주는 '{action}'만 체크리스트로 고정하세요. 욕심내서 여러 개 하면 다 흐려져요."),
    ("과제가 팀플이면 역할을 어떻게 나눠요?", "데이터/실험로그/발표/리팩터링으로 쪼개고 깃 이슈에 남기세요. 커밋이 기여 증명이 돼요."),
    ("막히면 교수님/조교님께 어떻게 물어봐요?", "재현 가능한 최소 예시+에러 메시지+환경(OS/파이썬)을 가져가세요. 코드 전체는 비효율적이에요."),
    ("학점이랑 대회/연구를 같이 해도 될까요?", "학기 중엔 수업 프로젝트를 포트폴리오 품질로 올리고, 대회는 방학 집중이 안전해요."),
    ("실험 로그는 어떻게 남겨요?", "날짜_실험명 폴더 + config + metrics + 짧은 메모.md요. 실패 실험도 남기세요."),
    ("논문은 어떻게 읽기 시작해요?", "문제정의→방법→실험→한계로 노트를 남기고, 그림 하나를 설명하면 발표형 시험에 강해요."),
    ("GPU 서버를 자주 놓치면요?", "공지 알람 + 스크립트 사전 준비 + 예약 직후 바로 제출. 낮 시간대 경쟁이 더 심할 수 있어요."),
    ("포트폴리오는 뭐가 설득력 있어요?", "수업 프로젝트 1 + 개인 미니 1을 깊게. 많이 만들기보다 하나를 설명하는 힘이 면접에서 버텨요."),
    ("표절/유사도 검사는 어떻게 피해요?", "친구 코드를 보지 말고 혼자 다시 구현하세요. 변수명만 바꾸는 건 위험해요."),
    ("연구실 메일엔 뭘 쓰나요?", "관심 논문 1~2편 기준 다섯 줄 + CV/깃허브 + 가능 시간. 성적만 나열하면 답장률이 낮아요."),
    ("기초가 부족한 느낌이면요?", "유행 프레임워크보다 확률·선형대수·알고리즘을 먼저 보강하세요. 상위에서 계속 발목을 잡아요."),
    ("LLM API만 쓰는 프로젝트는요?", "평가 지표·프롬프트 버전·실패 사례·비용/지연을 넣으면 학부 수준으로도 설득력이 생겨요."),
    ("팀원이 깃 충돌을 자주 내요.", "main 보호 + develop 브랜치, 큰 파일 제외. 충돌 시 파일 단위로 나누세요."),
    ("발표 슬라이드는 어떻게 짜요?", "직관 그림 1 + 실험 결과 1 + 한계/다음 질문. 수식 나열보다 기억에 남아요."),
    ("진로가 연구/개발 사이에서 흔들려요.", "짧은 학부연구와 인턴을 하나씩 해보세요. 논문이 즐거운지, 서비스가 즐거운지 몸이 알려줘요."),
]


def _food_chat(idx: int) -> dict:
    place, area, menu, price, wait = FOOD_PLACES[idx % len(FOOD_PLACES)]
    alt = FOOD_PLACES[(idx + 3) % len(FOOD_PLACES)][0]
    msgs: list[dict] = []

    def j(text: str) -> None:
        msgs.append({"senderRole": "junior", "text": text})

    def s(text: str) -> None:
        msgs.append({"senderRole": "senior", "text": text})

    j(f"선배, 서울대 근처에서 {menu} 먹을 만한 곳 찾아요. {area} 쪽이면 더 좋아요.")
    s(f"그러면 '{place}'부터 보세요. {area}에 있고 {menu}가 {price}예요. 참고로 {wait}라서 시간대만 피하면 됩니다.")
    j("와 구체적이네요. 제가 예산이랑 시간이 촉박해서 더 여쭤볼게요.")
    s(f"좋아요. 예산이 빠듯하면 {alt}도 후보로 두고, {place}는 '맛·분위기' 우선일 때 가세요.")

    # follow-up cascade to reach >= 30 messages
    follow = list(FOOD_FOLLOWUPS)
    RNG.shuffle(follow)
    for q, a in follow:
        j(q)
        s(
            a.format(
                place=place,
                area=area,
                menu=menu,
                wait=wait,
                alt=alt,
                reserve="예약이 안전해요" if "예약" in wait or "만석" in wait else "현장 대기도 가능해요",
            )
        )
        if len(msgs) >= MIN_MESSAGES:
            break

    while len(msgs) < MIN_MESSAGES:
        j("혹시 마지막으로 피해야 할 실수가 있을까요?")
        s(f"성급하게 리뷰 1등만 보지 말고, {wait} 같은 조건을 먼저 보세요. {place}도 피크엔 실망할 수 있어요.")
        j("팁 감사합니다. 메모해둘게요.")
        s("메모에 '시간대/예산/인원/포장여부' 네 가지만 적어두면 다음에도 고르기 쉬워요.")

    return {
        "id": f"food-{idx:03d}",
        "topic": "서울대_주변_맛집",
        "title": f"{area} · {place} · {menu}",
        "messages": msgs[: max(MIN_MESSAGES, len(msgs))],
    }


def _ai_chat(idx: int) -> dict:
    course, hard, tip, trap = AI_COURSES[idx % len(AI_COURSES)]
    msgs: list[dict] = []

    def j(text: str) -> None:
        msgs.append({"senderRole": "junior", "text": text})

    def s(text: str) -> None:
        msgs.append({"senderRole": "senior", "text": text})

    j(f"선배, 인공지능학과에서 '{course}' 관련해서 막혀서요. 어디서부터 손대야 할지 모르겠어요.")
    s(f"'{course}'는 {hard} 포인트가 커요. 먼저 '{tip}'부터 고정하세요. 흔한 함정은 '{trap}'입니다.")
    j("저도 과제만 급하게 손대고 있었어요. 조금 더 구체적으로 여쭤볼게요.")
    s("좋아요. 목표를 '완벽하게'가 아니라 '재현 가능한 최소 결과'로 바꾸면 속도가 납니다.")

    follow = list(AI_FOLLOWUPS)
    RNG.shuffle(follow)
    for q, a in follow:
        j(q)
        s(a.format(action=tip))
        if len(msgs) >= MIN_MESSAGES:
            break

    while len(msgs) < MIN_MESSAGES:
        j("이번 주 체크리스트로 정리해주실 수 있어요?")
        s(f"1) {tip} 2) 실패 로그 남기기 3) 질문 3개를 오피스아워용으로 적기. 이 세 개만 해도 {course}는 버팁니다.")
        j("감사합니다. 팀원에게도 공유할게요.")
        s("공유할 때 회의 시간과 담당까지 같이 적어두면 분쟁이 줄어요.")

    return {
        "id": f"ai-{idx:03d}",
        "topic": "인공지능학과_전공",
        "title": f"{course} · 학습/과제 상담",
        "messages": msgs[: max(MIN_MESSAGES, len(msgs))],
    }


def main() -> None:
    conversations: list[dict] = []
    half = NUM_CHATS // 2
    for i in range(1, half + 1):
        conversations.append(_food_chat(i))
    for i in range(1, half + 1):
        conversations.append(_ai_chat(i))

    # enforce min length
    for c in conversations:
        assert len(c["messages"]) >= MIN_MESSAGES, c["id"]

    flat_count = sum(len(c["messages"]) for c in conversations)
    payload = {
        "schema_version": 2,
        "description": "시연용 가상 선후배 '긴 채팅' 200개. 각 채팅 >=30 메시지. 주제: 서울대 맛집 / 인공지능학과.",
        "conversation_count": len(conversations),
        "message_count": flat_count,
        "min_messages_per_chat": MIN_MESSAGES,
        "conversations": conversations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"conversations={len(conversations)} messages={flat_count}")


if __name__ == "__main__":
    main()
