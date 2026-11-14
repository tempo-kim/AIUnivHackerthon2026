const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const suggestionList = document.getElementById("suggestion-list");
const resetBtn = document.getElementById("reset-btn");

const QA_DATA = [
  {
    keywords: ["전과", "복수전공", "학과"],
    answer:
      "전과를 고민하시면 모집 요강의 지원 학점/이수 과목 기준부터 먼저 확인하세요. 그다음 이번 학기에 필요한 선수과목을 최소 단위로 먼저 채우는 게 안전합니다. 전과 준비 일정표를 4주 단위로 쪼개서 관리하면 흔들림이 줄어요.",
  },
  {
    keywords: ["인턴", "취업", "면접", "자소서"],
    answer:
      "취업 준비는 목표 직무 공고 5개를 먼저 비교해서 공통 요구역량을 뽑는 방식이 가장 빠릅니다. 그 역량 기준으로 프로젝트/활동 경험을 2~3개만 깊게 정리해 자소서와 면접 답변을 맞춰보세요. 가능하면 이번 주 안에 공고 1건이라도 실제 지원해보는 걸 추천해요.",
  },
  {
    keywords: ["수강", "시간표", "학점"],
    answer:
      "시간표는 필수 과목과 난이도 높은 과목을 먼저 고정한 뒤, 남는 칸에 팀플 과목을 분산 배치하는 게 좋아요. 학점 관리는 시험 2주 전부터 과목별 체크리스트를 만들어 반복 복습 시간을 고정해두면 효과가 큽니다.",
  },
  {
    keywords: ["동아리", "학교생활", "친구", "적응"],
    answer:
      "학교 적응은 사람 만나는 채널을 2개만 꾸준히 잡는 게 핵심입니다. 예를 들어 전공 스터디 1개 + 동아리 1개처럼요. 첫 한 달은 모임 참석 빈도를 정해 루틴화하면 훨씬 빨리 자리 잡을 수 있어요.",
  },
];

const SUGGESTIONS = [
  "전과를 고민 중인데 무엇부터 준비해야 하나요?",
  "취업 준비를 이번 학기부터 하려면 어떻게 시작할까요?",
  "수강신청에서 망하지 않으려면 어떤 순서로 짜야 해요?",
];

function makeId() {
  return `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function appendMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role === "junior" ? "me" : "other"}`;
  bubble.textContent = text;
  bubble.dataset.id = makeId();
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function resetChat() {
  messagesEl.replaceChildren();
  appendMessage(
    "senior",
    "안녕하세요, AI 선배예요. 전과, 수강신청, 취업 준비처럼 자주 묻는 고민을 먼저 정리해서 안내해드릴게요."
  );
}

function scoreAnswer(question, item) {
  const q = question.toLowerCase();
  return item.keywords.reduce((acc, keyword) => (q.includes(keyword) ? acc + 1 : acc), 0);
}

function answerFromData(question) {
  const ranked = QA_DATA
    .map((item) => ({ item, score: scoreAnswer(question, item) }))
    .sort((a, b) => b.score - a.score);

  if (ranked[0].score <= 0) {
    return "좋은 질문이에요. 상황(학년/전공/지금 준비한 것)을 조금만 더 알려주시면, 데이터에 맞는 사례 기준으로 더 정확하게 정리해드릴게요.";
  }
  return ranked[0].item.answer;
}

function renderSuggestions() {
  suggestionList.replaceChildren(
    ...SUGGESTIONS.map((question) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-btn";
      button.textContent = question;
      button.addEventListener("click", () => {
        input.value = question;
        updateSendState();
        input.focus();
      });
      return button;
    })
  );
}

function updateSendState() {
  sendBtn.disabled = input.value.trim() === "";
}

function sendQuestion(text) {
  const message = text.trim();
  if (!message) return;
  appendMessage("junior", message);
  input.value = "";
  updateSendState();

  const answer = answerFromData(message);
  setTimeout(() => appendMessage("senior", answer), 350);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendQuestion(input.value);
});

input.addEventListener("input", updateSendState);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

resetBtn.addEventListener("click", resetChat);

renderSuggestions();
resetChat();
