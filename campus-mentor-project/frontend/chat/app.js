// 주소 예시: index.html?role=junior&mentor=1 (후배), index.html?role=senior&mentor=1 (선배)
// 같은 mentor 값이면 후배·선배가 같은 대화방을 씀
const ROLE_LABELS = { junior: "후배", senior: "선배" };

const params = new URLSearchParams(location.search);
const myRole = params.get("role");
const mentorNumber = Number(params.get("mentor"));
const mentor = MOCK_MENTORS[mentorNumber - 1];
const mentorId = String(mentorNumber);

const ERROR_MESSAGES = {
  load: "대화를 불러오지 못했어요. 네트워크 연결을 확인한 뒤 새로고침해 주세요.",
  send: "메시지를 보내지 못했어요. 네트워크 연결을 확인하고 다시 전송해 주세요.",
  sync: "새 메시지를 확인하지 못하고 있어요. 네트워크 연결을 확인해 주세요.",
};

const chatView = document.getElementById("chat-view");
const invalidView = document.getElementById("invalid-view");
const messagesEl = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const resetBtn = document.getElementById("reset-btn");
const errorBanner = document.getElementById("error-banner");

// 이미 화면에 그린 메시지 (같은 메시지가 두 번 그려지지 않게)
const shownIds = new Set();
let isSending = false;

function showError(text) {
  errorBanner.textContent = text;
  errorBanner.hidden = false;
}

function hideError() {
  errorBanner.hidden = true;
}

function renderHeader() {
  const badge = document.getElementById("role-badge");
  badge.className = `role-badge ${myRole}`;
  badge.textContent =
    myRole === "senior" ? `선배(${mentor.name})로 접속 중` : "후배로 접속 중";

  const avatar = document.getElementById("partner-avatar");
  const name = document.getElementById("partner-name");
  const meta = document.getElementById("partner-meta");
  const intro = document.getElementById("partner-intro");

  if (myRole === "junior") {
    avatar.textContent = mentor.name.charAt(0);
    avatar.style.background = mentor.color;
    name.textContent = `${mentor.name} 선배`;
    meta.textContent = `${mentor.grade} · ${mentor.major}`;
    intro.textContent = mentor.intro;
    input.placeholder = "선배에게 궁금한 점을 물어보세요";
  } else {
    avatar.textContent = "후";
    avatar.style.background = "#8a96a3";
    name.textContent = "후배";
    meta.textContent = "고민 상담을 요청한 후배";
    intro.textContent = "후배의 질문에 경험을 바탕으로 답해 주세요.";
    input.placeholder = "후배에게 답변을 보내 주세요";
  }
  document.title = `${name.textContent}와 대화`;
}

function showEmptyState() {
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent =
    myRole === "junior" ? "아직 대화가 없어요. 선배에게 먼저 질문해 보세요." : "아직 후배의 질문이 없어요.";
  messagesEl.appendChild(empty);
}

function appendMessage(message) {
  if (shownIds.has(message.id)) return;
  shownIds.add(message.id);
  messagesEl.querySelector(".empty-state")?.remove();

  const bubble = document.createElement("div");
  bubble.className = `bubble ${message.role === myRole ? "me" : "other"}`;
  bubble.textContent = message.text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderMessages(messages) {
  messagesEl.replaceChildren();
  shownIds.clear();
  if (messages.length === 0) showEmptyState();
  messages.forEach(appendMessage);
}

function updateSendState() {
  sendBtn.disabled = isSending || input.value.trim() === "";
}

function autoResize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

async function init() {
  if (!ROLE_LABELS[myRole] || !mentor) {
    invalidView.hidden = false;
    return;
  }

  chatView.hidden = false;
  renderHeader();
  resetBtn.hidden = !ChatApi.canClear;

  try {
    renderMessages(await ChatApi.getMessages(mentorId));
  } catch {
    renderMessages([]);
    showError(ERROR_MESSAGES.load);
  }

  ChatApi.subscribe(mentorId, {
    onMessage: appendMessage,
    onClear: () => renderMessages([]),
    onError: () => showError(ERROR_MESSAGES.sync),
    onRecover: hideError,
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || isSending) return; // 빈 메시지·중복 전송 방지

    isSending = true;
    updateSendState();
    try {
      appendMessage(await ChatApi.sendMessage(mentorId, myRole, text));
      hideError();
      input.value = "";
      autoResize();
    } catch {
      // 입력한 내용은 지우지 않아서 바로 다시 보낼 수 있음
      showError(ERROR_MESSAGES.send);
    } finally {
      isSending = false;
      updateSendState();
    }
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

  resetBtn.addEventListener("click", () => {
    if (!confirm("이 대화방의 메시지를 모두 지울까요? 상대 화면에서도 지워져요.")) return;
    ChatApi.clearMessages(mentorId);
    renderMessages([]);
  });
}

init();
