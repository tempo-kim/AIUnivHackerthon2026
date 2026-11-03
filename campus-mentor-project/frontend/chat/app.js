const REPLY_DELAY_MS = 1200;

const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("question");
const sendBtn = document.getElementById("send-btn");

function renderMentor(mentor) {
  document.getElementById("mentor-avatar").textContent = mentor.name.charAt(0);
  document.getElementById("mentor-name").textContent = mentor.name;
  document.getElementById("mentor-meta").textContent = `${mentor.grade} · ${mentor.major}`;
  document.getElementById("mentor-intro").textContent = mentor.intro;
}

function addBubble(text, who) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${who}`;
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

// 주제별로 몇 번 답했는지 기억해서 답변을 번갈아 보여줌
const answerCount = {};

function pickAnswer(question) {
  const text = question.replace(/\s+/g, "").toLowerCase();
  const match = MOCK_TOPICS.find((t) => t.keywords.some((k) => text.includes(k)));
  if (!match) return FALLBACK_ANSWER;

  const count = answerCount[match.topic] || 0;
  answerCount[match.topic] = count + 1;
  return match.answers[count % match.answers.length];
}

function updateSendState() {
  sendBtn.disabled = input.value.trim() === "";
}

function autoResize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return; // 빈 질문 방지

  addBubble(question, "me");
  input.value = "";
  autoResize();
  updateSendState();

  const typing = addBubble("입력 중…", "mentor typing");
  setTimeout(() => {
    typing.remove();
    addBubble(pickAnswer(question), "mentor");
  }, REPLY_DELAY_MS);
});

input.addEventListener("input", () => {
  updateSendState();
  autoResize();
});

// Enter 전송, Shift+Enter 줄바꿈 (한글 조합 중 Enter는 무시)
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});

renderMentor(MOCK_MENTOR);
addBubble(`안녕하세요, ${MOCK_MENTOR.name}입니다. 무엇이든 물어보세요!`, "mentor");
