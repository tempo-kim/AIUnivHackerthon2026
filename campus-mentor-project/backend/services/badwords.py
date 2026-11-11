"""채팅·닉네임·소개·신고 상세의 욕설 검사.

정규화한 세 가지 버전 중 하나라도 금지어를 포함하면 걸린다.
1) 소문자화 + 공백·특수문자·이모지 제거
2) 1)에서 숫자까지 제거
3) 1)에서 같은 글자 반복을 한 글자로 축약 (ㅅㅅㅅㅂ → ㅅㅂ)
허용 예외(시발점, 새끼손가락 등)는 검사 전에 지운다.
frontend/chat/badwords.js에 같은 목록이 복사돼 있으니 바꿀 때 함께 바꿀 것.
"""

from __future__ import annotations

import re

BADWORDS = [
    "시발", "씨발", "씨바", "시바", "씨빨", "시빨", "쉬발", "쒸발", "씨팔", "시팔", "씹", "씹새", "씹창",
    "좆", "좃", "존나", "졸라", "좆같", "좆밥", "개새끼", "개새기", "개색기", "개색끼", "개세끼", "새끼야",
    "니새끼", "느금마", "느금", "니애미", "니에미", "니미", "애미", "애비", "엠창", "병신", "븅신", "빙신",
    "병싄", "등신", "미친놈", "미친년", "미친새끼", "또라이", "돌아이", "꺼져", "닥쳐", "지랄", "염병", "썅",
    "쌍놈", "쌍년", "개놈", "개년", "화냥년", "걸레년", "창녀", "보지", "자지", "섹스", "야동", "장애인새끼",
    "애자", "찐따", "한남충", "김치녀", "맘충", "틀딱", "급식충", "죽어라", "뒤져", "뒤질래", "죽여버", "자살해",
    "ㅅㅂ", "ㅆㅂ", "ㅅㅍ", "ㅆㅍ", "ㅂㅅ", "ㅄ", "ㅈㄹ", "ㅈㄴ", "ㅁㅊ", "ㄲㅈ", "ㄷㅊ", "ㅗ",
    "씨8", "시8", "18놈", "18년", "개18", "tlqkf", "qudtls", "wlfkf",
    "fuck", "fck", "fuk", "shit", "bitch", "asshole", "damn", "motherfucker",
]

# 검사 전에 지우는 정상 표현
ALLOWED = ["시발점", "시발역", "병신년", "새끼손가락", "새끼발가락", "미친듯이", "수박씨", "씨발라"]

_KEEP = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]")
_DIGITS = re.compile(r"[0-9]")
_REPEAT = re.compile(r"(.)\1+")


def _clean(text: str) -> str:
    """소문자화하고 한글·영문·숫자 외(공백, 특수문자, 이모지, 한자)를 지운다."""
    return _KEEP.sub("", (text or "").lower())


def _remove_allowed(text: str) -> str:
    for word in ALLOWED:
        text = text.replace(word, "")
    return text


def _variants(text: str) -> list[str]:
    base = _remove_allowed(_clean(text))
    no_digits = _remove_allowed(_DIGITS.sub("", base))
    collapsed = _remove_allowed(_REPEAT.sub(r"\1", base))
    return [base, no_digits, collapsed]


def contains_badword(text: str) -> bool:
    return any(word in variant for variant in _variants(text) for word in BADWORDS)
