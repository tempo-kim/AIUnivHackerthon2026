# Frontend 개발 가이드

시스템 전체 흐름, API 요청·응답, SQLite와 인증 방식은 [프로젝트 README](../README.md)를 참고하세요.

## 화면과 파일

| 파일 | 기능 |
| --- | --- |
| `main.html` | 학교·학적·도움 분야 선택, 후배 가입/로그인, 선배 가입/로그인, 고민 입력 |
| `result/index.html` | 추천 목록·관심 목록, 다음 추천 요청, 로그인한 후배의 채팅 기록 목록 |
| `chat/index.html` | 선배/후배 채팅 및 선배 받은 대화함 화면 |
| `chat/app.js` | 채팅 상태, 메시지 UI, 종료·신고 동작 |
| `chat/api.js` | 메시지/대화 목록/종료 상태 API 및 인증 토큰 연결 |
| `assets/achievements.js` | 업적 목록·달성 토스트·후배 채팅 기록 기준 동기화 |

## 브라우저 상태

- 후배 로그인 세션: `localStorage`의 `ppunppun-junior-session`
- 선배 로그인 세션: `localStorage`의 `ppunppun-senior-session`
- 고민 및 최근 매칭 응답: 현재 탭의 `sessionStorage` (`ppunppun-concern`, `ppunppun-choice`, `ppunppun-match`)
- 다음 추천에서 제외할 선배 ID: 현재 탭의 `sessionStorage` (`ppunppun-seen-mentors`)
- 관심 선배: 사용자 ID별 `localStorage` (`ppunppun-favorites-v1:<junior_id>`)
- 업적 표시 상태: 사용자 ID별 브라우저 저장소. 첫걸음·인연 탐험가는 `/api/junior-achievements` 결과와 동기화합니다.

로그인 토큰은 API 요청의 Bearer 인증에 사용합니다. 토큰, PIN, API 키를 화면에 노출하거나 코드·로그에 출력하지 마세요.

## 채팅 및 다시 추천받기

채팅 API 기본 설정은 서버 모드입니다(`chat/api.js`의 `USE_MOCK = false`). 메시지는 백엔드 SQLite에 저장되고 채팅 화면은 서버를 주기적으로 조회합니다. 후배가 대화를 종료하면 추천 결과로 돌아옵니다. 종료된 대화도 하단 채팅 메뉴의 이력에서 다시 열어 읽을 수 있습니다.

`다른 선배 보기`는 지금까지 본 선배 ID를 제외해 `/api/match`에 다음 후보 3명을 요청합니다. 후배가 새 고민으로 다시 매칭을 시작하면 제외 목록이 초기화됩니다. 자세한 재요청 본문은 루트 README의 **다음 3명 추천 API** 절에 있습니다.
