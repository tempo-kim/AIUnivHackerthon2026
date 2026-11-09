// 주소 예시: index.html?role=junior&mentor=1 (후배), index.html?role=senior&mentor=1 (선배)
// 같은 mentor 값이면 후배·선배가 같은 대화방을 씀
const CONNECT_LOADING_MS = 3000; // 첫 진입 "연결중" 로딩 시간
const ROLE_LABELS = { junior: "후배", senior: "선배" };
const REACTIONS = ["👍", "✅", "❤️", "😂", "🙏", "👏", "감사합니다!", "확인했어요!"];

// 첫 질문 추천 문장 (템플릿). keyword가 후배의 고민에 있으면 먼저 보여줌
const TOPIC_QUESTIONS = {
  동아리: { keyword: "동아리", question: "선배님은 동아리를 어떻게 고르고 시작하셨어요?" },
  "취업 준비": { keyword: "취업", question: "선배님은 취업 준비를 어떻게 시작하셨어요?" },
  인턴: { keyword: "인턴", question: "선배님은 인턴 지원을 어떻게 준비하셨어요?" },
  공모전: { keyword: "공모전", question: "선배님은 공모전 팀을 어떻게 꾸려서 준비하셨어요?" },
  연구실: { keyword: "연구", question: "선배님은 연구실 경험을 어떻게 시작하셨어요?" },
  "대학원 준비": { keyword: "대학원", question: "선배님은 대학원 준비를 어떻게 시작하셨어요?" },
  학생회: { keyword: "학생회", question: "학생회 활동이 학교생활에 어떤 도움이 되었는지 궁금해요." },
};
const REASON_QUESTIONS = {
  학교적응: "학교에 적응할 때 제일 도움이 됐던 건 뭐였어요?",
  "밥집 추천": "선배님이 자주 가시는 학교 근처 밥집을 추천해 주실 수 있어요?",
  전공지식: "전공 공부는 어떤 순서로 하면 좋을까요?",
  "진로와 취업": "진로를 정할 때 선배님은 무엇을 가장 먼저 해 보셨어요?",
  대외활동: "처음 해 볼 만한 대외활동을 추천해 주실 수 있어요?",
};
const GENERIC_QUESTIONS = [
  "제 시기에 미리 해 두면 좋은 일이 있을까요?",
  "학교 다니면서 가장 잘했다고 생각하는 일은 뭐예요?",
  "지금 돌아보면 다르게 해 보고 싶은 일이 있으세요?",
];
const SINGLE_EMOJI =
  /^(?:\p{Regional_Indicator}{2}|\p{Extended_Pictographic}(?:️|\p{Emoji_Modifier})?(?:‍\p{Extended_Pictographic}(?:️|\p{Emoji_Modifier})?)*)$/u;

const params = new URLSearchParams(location.search);
const myRole = params.get("role");
const partnerRole = myRole === "junior" ? "senior" : "junior";
const mentorId = params.get("mentor") || "";
let mentor = null;

const ERROR_MESSAGES = {
  load: "대화를 불러오지 못했어요. 네트워크 연결을 확인한 뒤 새로고침해 주세요.",
  send: "메시지를 보내지 못했어요. 네트워크 연결을 확인하고 다시 전송해 주세요.",
  sync: "새 메시지를 확인하지 못하고 있어요. 네트워크 연결을 확인해 주세요.",
  end: "대화 종료 요청을 처리하지 못했어요. 네트워크 연결을 확인하고 다시 시도해 주세요.",
  report: "신고를 접수하지 못했어요. 네트워크 연결을 확인하고 다시 시도해 주세요.",
};

const $ = (id) => document.getElementById(id);
const loadingView = $("loading-view");
const chatView = $("chat-view");
const invalidView = $("invalid-view");
const messagesEl = $("messages");
const form = $("composer");
const input = $("message-input");
const sendBtn = $("send-btn");
const resetBtn = $("reset-btn");
const reportBtn = $("report-btn");
const endBtn = $("end-btn");
const errorBanner = $("error-banner");
const noticeBanner = $("notice-banner");
const suggestionsEl = $("suggestions");
const suggestionList = $("suggestion-list");
const reactionArea = $("composer-area");
const reactionToggle = $("reaction-toggle");
const reactionPanel = $("reaction-panel");

const reportModal = $("report-modal");
const reportForm = $("report-form");
const reportDetails = $("report-details");
const reportError = $("report-error");
const reportSubmit = $("report-submit");
const reportDone = $("report-done");

const endRequestModal = $("end-request-modal");

// 이미 화면에 그린 메시지 (같은 메시지가 두 번 그려지지 않게)
const shownIds = new Set();
let isSending = false;
let endState = { status: "active", requestedBy: null, declinedBy: null };

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function showError(text) {
  errorBanner.textContent = text;
  errorBanner.hidden = false;
}

function hideError() {
  errorBanner.hidden = true;
}

function showNotice(text) {
  noticeBanner.textContent = text;
  noticeBanner.hidden = !text;
}

// ---- 화면 그리기 ----
function renderHeader() {
  const badge = $("role-badge");
  badge.className = `role-badge ${myRole}`;
  badge.textContent = `${ROLE_LABELS[myRole]}로 접속 중`;

  const avatar = $("partner-avatar");
  const name = $("partner-name");
  const meta = $("partner-meta");
  const intro = $("partner-intro");

  if (myRole === "junior") {
    avatar.textContent = mentor.name.charAt(0);
    avatar.style.background = mentor.color;
    name.textContent = `${mentor.name} 선배`;
    meta.textContent = `${mentor.grade} · ${mentor.major}`;
    intro.textContent = mentor.intro;
    input.placeholder = "선배에게 궁금한 점을 물어보세요";
  } else {
    avatar.textContent = "후";
    avatar.style.background = "var(--navy)";
    name.textContent = "후배";
    meta.textContent = `${mentor.name} 선배에게 상담을 요청한 후배`;
    intro.textContent = "후배의 질문에 경험을 바탕으로 답해 주세요.";
    input.placeholder = "후배에게 답변을 보내 주세요";
  }
  document.title = `뻔뻔하게 · ${name.textContent}와 대화`;
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
  const emojiOnly = SINGLE_EMOJI.test(message.text.trim());
  bubble.className = `bubble ${message.role === myRole ? "me" : "other"}${emojiOnly ? " emoji-only" : ""}`;
  bubble.textContent = message.text;
  // 종료 안내는 항상 맨 아래에 두기
  messagesEl.insertBefore(bubble, messagesEl.querySelector(".ended-card"));
  messagesEl.scrollTop = messagesEl.scrollHeight;
  updateSuggestions();
}

function renderMessages(messages) {
  messagesEl.replaceChildren();
  shownIds.clear();
  if (messages.length === 0) showEmptyState();
  messages.forEach(appendMessage);
  updateSuggestions();
}

function updateSendState() {
  const ended = endState.status === "ended";
  input.disabled = ended;
  sendBtn.disabled = ended || isSending || input.value.trim() === "";
  reactionToggle.disabled = ended || isSending;
  if (ended) closeReactionPanel();
}

function autoResize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

// ---- 첫 질문 추천 (후배 화면) ----
function readConcern() {
  try {
    return sessionStorage.getItem("ppunppun-concern") || "";
  } catch {
    return "";
  }
}

// CSV의 "공모전 (교내, 교외)"가 쉼표로 잘려 들어오므로 앞부분만 쓰고 조각은 버림
function cleanTopics(topics) {
  const names = topics
    .filter((topic) => !topic.includes(")"))
    .map((topic) => topic.split("(")[0].trim())
    .filter((topic) => topic && topic !== "others" && topic !== "없음");
  return [...new Set(names)];
}

function buildSuggestions() {
  const concern = readConcern();
  const reason = Object.keys(REASON_QUESTIONS).find((key) => concern.includes(key));
  const topicItems = cleanTopics(mentor.helpTopics).map(
    (topic) => TOPIC_QUESTIONS[topic] ?? { keyword: topic, question: `선배님은 ${topic} 경험을 어떻게 시작하셨어요?` }
  );
  // 고민에 나온 주제를 앞으로 (같은 조건이면 원래 순서 유지)
  const matched = topicItems.filter((item) => concern.includes(item.keyword));
  const others = topicItems.filter((item) => !concern.includes(item.keyword));
  const questions = [
    ...(reason ? [REASON_QUESTIONS[reason]] : []),
    ...[...matched, ...others].map((item) => item.question),
    ...GENERIC_QUESTIONS,
  ];
  return questions.slice(0, 3);
}

function renderSuggestions() {
  if (myRole !== "junior") return;
  suggestionList.replaceChildren(
    ...buildSuggestions().map((question) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-btn";
      button.textContent = question;
      button.addEventListener("click", () => {
        // 바로 보내지 않고 입력창에 채워서 고칠 수 있게 함
        input.value = question;
        autoResize();
        updateSendState();
        input.focus();
        input.setSelectionRange(question.length, question.length);
      });
      return button;
    })
  );
}

function updateSuggestions() {
  suggestionsEl.hidden = !(myRole === "junior" && shownIds.size === 0 && endState.status !== "ended");
}

// ---- 빠른 반응 ----
function renderReactionPanel() {
  reactionPanel.replaceChildren(
    ...REACTIONS.map((reaction) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = reaction.length <= 2 ? "reaction-btn" : "reaction-btn text";
      button.textContent = reaction;
      button.addEventListener("click", () => sendText(reaction));
      return button;
    })
  );
}

function closeReactionPanel() {
  reactionPanel.hidden = true;
  reactionToggle.setAttribute("aria-expanded", "false");
}

function toggleReactionPanel() {
  reactionPanel.hidden = !reactionPanel.hidden;
  reactionToggle.setAttribute("aria-expanded", String(!reactionPanel.hidden));
}

// 일반 입력과 빠른 반응이 함께 쓰는 전송. 성공하면 true
async function sendText(text) {
  closeReactionPanel();
  if (!text || isSending || endState.status === "ended") return false; // 빈 메시지·중복 전송 방지

  isSending = true;
  updateSendState();
  try {
    appendMessage(await ChatApi.sendMessage(mentorId, myRole, text));
    hideError();
    return true;
  } catch {
    // 입력한 내용은 지우지 않아서 바로 다시 보낼 수 있음
    showError(ERROR_MESSAGES.send);
    return false;
  } finally {
    isSending = false;
    updateSendState();
  }
}

// ---- 대화 종료 ----
// live: 지금 막 바뀐 상태인지 (새로고침으로 불러온 상태면 거절 안내를 다시 띄우지 않음)
function applyEndState(state, { live = false } = {}) {
  endState = state;
  const { status, requestedBy, declinedBy } = state;

  endRequestModal.hidden = !(status === "pending" && requestedBy === partnerRole);
  if (!endRequestModal.hidden) {
    $("end-request-text").textContent = `${ROLE_LABELS[partnerRole]}가 대화 종료를 요청하였습니다. 동의합니까?`;
  }

  endBtn.disabled = status !== "active";
  messagesEl.querySelector(".ended-card")?.remove();

  if (status === "ended") {
    showNotice("");
    const card = document.createElement("div");
    card.className = "ended-card";
    card.innerHTML = '<img src="assets/logo.png" alt="뻔뻔하게" /><p>대화를 종료합니다</p>';
    messagesEl.querySelector(".empty-state")?.remove();
    messagesEl.appendChild(card);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    input.value = "";
    input.placeholder = "종료된 대화입니다";
  } else if (status === "pending" && requestedBy === myRole) {
    showNotice(`${ROLE_LABELS[partnerRole]}에게 대화 종료를 요청했어요. 응답을 기다리는 중이에요.`);
  } else if (status === "active" && live && declinedBy === partnerRole) {
    showNotice(`${ROLE_LABELS[partnerRole]}가 대화 종료를 거절했어요. 대화를 계속할 수 있어요.`);
  } else {
    showNotice("");
  }
  updateSendState();
  updateSuggestions();
}

async function runEndAction(action) {
  try {
    applyEndState(await action(), { live: true });
    hideError();
  } catch {
    showError(ERROR_MESSAGES.end);
  }
}

// ---- 신고 ----
function openReportModal() {
  reportForm.reset();
  reportError.hidden = true;
  reportForm.hidden = false;
  reportDone.hidden = true;
  reportModal.hidden = false;
  reportForm.querySelector("input[name=reason]").focus();
}

function closeReportModal() {
  reportModal.hidden = true;
  reportBtn.focus();
}

async function handleReportSubmit(e) {
  e.preventDefault();
  const reason = reportForm.querySelector("input[name=reason]:checked")?.value;
  const details = reportDetails.value.trim();
  const errors = [];
  if (!reason) errors.push("신고 사유를 선택해 주세요.");
  if (!details) errors.push("상세 내용을 입력해 주세요.");
  reportError.textContent = errors.join(" ");
  reportError.hidden = errors.length === 0;
  if (errors.length > 0) return;

  reportSubmit.disabled = true;
  try {
    await ChatApi.submitReport(mentorId, myRole, reason, details);
    reportForm.hidden = true;
    reportDone.hidden = false;
    $("report-close").focus();
  } catch {
    reportError.textContent = ERROR_MESSAGES.report;
    reportError.hidden = false;
  } finally {
    reportSubmit.disabled = false;
  }
}

// ---- 시작 ----
function bindEvents() {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (await sendText(input.value.trim())) {
      input.value = "";
      autoResize();
      updateSendState();
    }
  });

  reactionToggle.addEventListener("click", toggleReactionPanel);
  document.addEventListener("click", (e) => {
    if (!reactionPanel.hidden && !reactionArea.contains(e.target)) closeReactionPanel();
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
    if (!confirm("이 대화방의 메시지와 종료 상태를 모두 지울까요? 상대 화면에서도 지워져요.")) return;
    ChatApi.clearMessages(mentorId);
    renderMessages([]);
    applyEndState({ status: "active", requestedBy: null, declinedBy: null });
  });

  endBtn.addEventListener("click", () => {
    if (!confirm(`${ROLE_LABELS[partnerRole]}에게 대화 종료를 요청할까요?`)) return;
    runEndAction(() => ChatApi.requestEnd(mentorId, myRole));
  });
  $("end-agree").addEventListener("click", () => runEndAction(() => ChatApi.respondEnd(mentorId, myRole, true)));
  $("end-decline").addEventListener("click", () => runEndAction(() => ChatApi.respondEnd(mentorId, myRole, false)));

  reportBtn.addEventListener("click", openReportModal);
  reportForm.addEventListener("submit", handleReportSubmit);
  $("report-cancel").addEventListener("click", closeReportModal);
  $("report-close").addEventListener("click", closeReportModal);
  reportModal.addEventListener("click", (e) => {
    if (e.target === reportModal) closeReportModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !reportModal.hidden) closeReportModal();
    if (e.key === "Escape") closeReactionPanel();
  });
}

async function init() {
  if (!ROLE_LABELS[myRole] || !mentorId) {
    loadingView.hidden = true;
    invalidView.hidden = false;
    return;
  }

  try {
    const response = await fetch(`/api/mentors`);
    if (!response.ok) throw new Error();
    const mentors = await response.json();
    const found = mentors.find((item) => String(item.mentor_id) === String(mentorId));
    if (!found) throw new Error();
    mentor = {
      name: found.display_name || found.mentor_id,
      major: found.major,
      grade: "선배",
      intro: found.bio || found.help_topics?.join(" · ") || "후배의 고민을 함께 들어드려요.",
      color: "var(--blue)",
      helpTopics: found.help_topics ?? [],
    };
  } catch {
    loadingView.hidden = true;
    invalidView.hidden = false;
    return;
  }

  $("loading-text").textContent = `${ROLE_LABELS[partnerRole]}와 연결중입니다`;
  renderHeader();
  renderSuggestions();
  renderReactionPanel();
  resetBtn.hidden = !ChatApi.canClear;

  // 로딩을 보여주는 동안 대화와 종료 상태를 미리 불러옴
  const [messagesResult, endStateResult] = await Promise.allSettled([
    ChatApi.getMessages(mentorId),
    ChatApi.getEndState(mentorId),
    delay(CONNECT_LOADING_MS),
  ]);

  loadingView.hidden = true;
  chatView.hidden = false;

  renderMessages(messagesResult.status === "fulfilled" ? messagesResult.value : []);
  if (endStateResult.status === "fulfilled") applyEndState(endStateResult.value);
  if (messagesResult.status === "rejected" || endStateResult.status === "rejected") {
    showError(ERROR_MESSAGES.load);
  }

  ChatApi.subscribe(mentorId, {
    onMessage: appendMessage,
    onClear: () => {
      renderMessages([]);
      applyEndState({ status: "active", requestedBy: null, declinedBy: null });
    },
    onEndState: (state) => applyEndState(state, { live: true }),
    onError: () => showError(ERROR_MESSAGES.sync),
    onRecover: hideError,
  });

  bindEvents();
}

init();
