# 시연용 데이터

| 파일 | 용도 |
|------|------|
| `Mentors.csv` / `Mentors.add.csv` | 선배 프로필 |
| `school_bot_seed_chats.json` | 학교 챗봇용 **가상 선후배 채팅** (~220메시지) |
| `raw/` | Syntitan 넣기 전 원본 (개인정보 금지) |

## 학교 챗봇 시드

`school_bot_seed_chats.json`은 시연을 위한 가상 대화입니다.

- 주제 1: 서울대학교 주변 맛집 (구체적 거리·가격·웨이팅·주문 팁)
- 주제 2: 인공지능학과 전공 질문 (과제·수강·연구실·실험 팁)

재생성:
```bash
cd campus-mentor-project/backend
python scripts/generate_school_bot_seed.py
```

실제 학생 개인정보가 아닙니다. 공개 저장소에 실명·연락처를 넣지 마세요.
