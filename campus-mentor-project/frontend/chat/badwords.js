// 욕설 검사 (USE_MOCK 모드용). backend/services/badwords.py와 같은 목록·규칙이니 바꿀 때 함께 바꿀 것
// 정규화 세 가지 중 하나라도 금지어를 포함하면 걸림
// 1) 소문자화 + 공백·특수문자·이모지 제거  2) 1에서 숫자 제거  3) 1에서 반복 글자 축약(ㅅㅅㅅㅂ → ㅅㅂ)
const BadWords = (() => {
  const BADWORDS = [
    "시발", "씨발", "씨바", "시바", "씨빨", "시빨", "쉬발", "쒸발", "씨팔", "시팔", "씹", "씹새", "씹창",
    "좆", "좃", "존나", "졸라", "좆같", "좆밥", "개새끼", "개새기", "개색기", "개색끼", "개세끼", "새끼야",
    "니새끼", "느금마", "느금", "니애미", "니에미", "니미", "애미", "애비", "엠창", "병신", "븅신", "빙신",
    "병싄", "등신", "미친놈", "미친년", "미친새끼", "또라이", "돌아이", "꺼져", "닥쳐", "지랄", "염병", "썅",
    "쌍놈", "쌍년", "개놈", "개년", "화냥년", "걸레년", "창녀", "보지", "자지", "섹스", "야동", "장애인새끼",
    "애자", "찐따", "한남충", "김치녀", "맘충", "틀딱", "급식충", "죽어라", "뒤져", "뒤질래", "죽여버", "자살해",
    "ㅅㅂ", "ㅆㅂ", "ㅅㅍ", "ㅆㅍ", "ㅂㅅ", "ㅄ", "ㅈㄹ", "ㅈㄴ", "ㅁㅊ", "ㄲㅈ", "ㄷㅊ", "ㅗ",
    "씨8", "시8", "18놈", "18년", "개18", "tlqkf", "qudtls", "wlfkf",
    "fuck", "fck", "fuk", "shit", "bitch", "asshole", "damn", "motherfucker",
  ];
  // 검사 전에 지우는 정상 표현
  const ALLOWED = ["시발점", "시발역", "병신년", "새끼손가락", "새끼발가락", "미친듯이", "수박씨", "씨발라"];

  const clean = (text) => String(text ?? "").toLowerCase().replace(/[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]/g, "");
  const removeAllowed = (text) => ALLOWED.reduce((acc, word) => acc.split(word).join(""), text);

  function variants(text) {
    const base = removeAllowed(clean(text));
    return [base, removeAllowed(base.replace(/[0-9]/g, "")), removeAllowed(base.replace(/(.)\1+/g, "$1"))];
  }

  function contains(text) {
    return variants(text).some((variant) => BADWORDS.some((word) => variant.includes(word)));
  }

  return { contains, CHAT_MESSAGE: "부적절한 채팅입니다. 바른 표현을 사용해 주세요." };
})();
