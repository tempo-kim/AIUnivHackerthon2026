// 대화 관련 API 호출을 한곳에 모은 파일.
// USE_MOCK=true  → 서버 없이 chat-store.js(localStorage + BroadcastChannel) 사용
// USE_MOCK=false → API_BASE_URL의 백엔드 API 호출
// API 키나 비밀번호는 절대 이 파일(프론트엔드)에 넣지 말 것
const API_BASE_URL = ""; // FastAPI가 제공하는 /frontend 경로에서 상대 API를 호출
const USE_MOCK = false;

const REQUEST_TIMEOUT_MS = 10000;
const POLL_INTERVAL_MS = 3000; // 서버 모드에서 새 메시지를 확인하는 간격

const ChatApi = (() => {
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...options.headers },
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
      return res.status === 204 ? null : await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  // 서버 응답 형식이 조금 달라도 화면에서 쓰는 형태 { id, role, text, sentAt }로 맞춤
  function normalizeMessage(raw) {
    return {
      id: String(raw.id ?? raw.messageId ?? `${raw.senderRole}-${raw.createdAt}-${raw.text}`),
      role: raw.senderRole ?? raw.role,
      text: raw.text,
      sentAt: raw.createdAt ?? raw.sentAt ?? Date.now(),
    };
  }

  function roomIdOf(mentorId) {
    return `mentor-${mentorId}`;
  }

  // POST /api/messages
  async function sendMessage(mentorId, senderRole, text) {
    if (USE_MOCK) return ChatStore.sendMessage(roomIdOf(mentorId), { role: senderRole, text });

    const data = await request("/api/messages", {
      method: "POST",
      body: JSON.stringify({ mentorId: String(mentorId), senderRole, text }),
    });
    // 서버가 저장된 메시지를 돌려주지 않으면 보낸 내용으로 화면에 표시
    return normalizeMessage(data?.message ?? data ?? { senderRole, text, createdAt: Date.now() });
  }

  // GET /api/messages?mentorId=1
  async function getMessages(mentorId) {
    if (USE_MOCK) return ChatStore.loadMessages(roomIdOf(mentorId));

    const data = await request(`/api/messages?mentorId=${encodeURIComponent(mentorId)}`);
    const list = Array.isArray(data) ? data : data?.messages ?? [];
    return list.map(normalizeMessage);
  }

  // ---- 대화 종료 ----
  // 상태 형식: { status: "active" | "pending" | "ended", requestedBy, declinedBy }
  function normalizeEndState(raw) {
    return {
      status: raw?.status ?? "active",
      requestedBy: raw?.requestedBy ?? null,
      declinedBy: raw?.declinedBy ?? null,
    };
  }

  // GET /api/chat-end?mentorId=1
  async function getEndState(mentorId) {
    if (USE_MOCK) return ChatStore.loadEndState(roomIdOf(mentorId));
    return normalizeEndState(await request(`/api/chat-end?mentorId=${encodeURIComponent(mentorId)}`));
  }

  // POST /api/chat-end/request  body: {"mentorId":"1","requesterRole":"junior"}
  async function requestEnd(mentorId, requesterRole) {
    if (USE_MOCK) return ChatStore.requestEnd(roomIdOf(mentorId), requesterRole);
    const data = await request("/api/chat-end/request", {
      method: "POST",
      body: JSON.stringify({ mentorId: String(mentorId), requesterRole }),
    });
    return normalizeEndState(data);
  }

  // POST /api/chat-end/respond  body: {"mentorId":"1","responderRole":"senior","agree":true}
  async function respondEnd(mentorId, responderRole, agree) {
    if (USE_MOCK) return ChatStore.respondEnd(roomIdOf(mentorId), responderRole, agree);
    const data = await request("/api/chat-end/respond", {
      method: "POST",
      body: JSON.stringify({ mentorId: String(mentorId), responderRole, agree }),
    });
    return normalizeEndState(data);
  }

  // ---- 신고 ----
  // POST /api/reports  body: {"mentorId":"1","reporterRole":"junior","reason":"욕설·비방","details":"..."}
  async function submitReport(mentorId, reporterRole, reason, details) {
    const report = { mentorId: String(mentorId), reporterRole, reason, details };
    if (USE_MOCK) return ChatStore.saveReport(report);
    return request("/api/reports", { method: "POST", body: JSON.stringify(report) });
  }

  // 상대가 보낸 새 메시지·종료 상태 받기. 목 모드는 BroadcastChannel, 서버 모드는 주기적 조회
  function subscribe(mentorId, { onMessage, onClear, onEndState, onError, onRecover }) {
    if (USE_MOCK) return ChatStore.subscribe(roomIdOf(mentorId), { onMessage, onClear, onEndState });

    let failed = false;
    let lastEndState = "";
    const timer = setInterval(async () => {
      try {
        const [messages, endState] = await Promise.all([getMessages(mentorId), getEndState(mentorId)]);
        messages.forEach(onMessage);
        const endStateKey = JSON.stringify(endState);
        if (endStateKey !== lastEndState) {
          lastEndState = endStateKey;
          onEndState?.(endState);
        }
        if (failed) onRecover?.();
        failed = false;
      } catch (err) {
        failed = true;
        onError?.(err);
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }

  // 대화 초기화는 아직 서버 API가 없어 목 모드에서만 지원
  const canClear = USE_MOCK;

  function clearMessages(mentorId) {
    if (USE_MOCK) ChatStore.clearMessages(roomIdOf(mentorId));
  }

  return {
    sendMessage,
    getMessages,
    getEndState,
    requestEnd,
    respondEnd,
    submitReport,
    subscribe,
    clearMessages,
    canClear,
  };
})();
