# 시연용 데이터

| 파일 | 용도 |
|------|------|
| `Mentors.csv` / `Mentors.add.csv` | 선배 프로필 |
| `school_bot_seed_chats.json` | 학교 챗봇용 **가상 선후배 채팅** (~220메시지) |
| `raw/` | Syntitan 넣기 전 원본 (개인정보 금지) |

## 학교 챗봇 시드

`school_bot_seed_chats.json`은 시연용 **긴 채팅 200개**입니다.

- 채팅 100개: 서울대 주변 맛집 (각 채팅 ≥30메시지)
- 채팅 100개: 인공지능학과 전공 (각 채팅 ≥30메시지)
- 단순 Q&A 1회성이 아니라, 한 주제 안에서 후속 질문·조건 확인이 이어짐

재생성:
```bash
cd campus-mentor-project/backend
python scripts/generate_school_bot_seed.py
```

실제 학생 개인정보가 아닙니다.
