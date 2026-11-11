// 서버 없이 쓰는 가짜(목) 메시지 저장소. api.js에서 USE_MOCK=true일 때만 사용.
// localStorage(저장) + BroadcastChannel(같은 브라우저의 다른 탭으로 실시간 전달)
const ChatStore = (() => {
  const STORAGE_PREFIX = "campus-mentor-chat:";
  const END_STATE_PREFIX = "campus-mentor-chat-end:";
  const REPORTS_KEY = "campus-mentor-reports";
  const channels = {};

  function readJson(key, fallback) {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 실시간 전달만 동작
    }
  }

  function removeKey(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      // 무시
    }
  }

  function getChannel(roomId) {
    if (!("BroadcastChannel" in window)) return null;
    if (!channels[roomId]) channels[roomId] = new BroadcastChannel(`campus-mentor-chat-${roomId}`);
    return channels[roomId];
  }

  function createId() {
    return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  // 대화방의 저장된 메시지 목록
  function loadMessages(roomId) {
    return readJson(STORAGE_PREFIX + roomId, []);
  }

  function saveMessages(roomId, messages) {
    writeJson(STORAGE_PREFIX + roomId, messages);
  }

  // 메시지를 저장하고 상대 탭에 전달한 뒤, 만들어진 메시지를 돌려줌
  function sendMessage(roomId, { role, text }) {
    const message = { id: createId(), role, text, sentAt: Date.now() };
    saveMessages(roomId, [...loadMessages(roomId), message]);
    getChannel(roomId)?.postMessage({ type: "message", message });
    return message;
  }

  // 메시지와 종료 상태를 모두 지움 (테스트용 초기화)
  function clearMessages(roomId) {
    removeKey(STORAGE_PREFIX + roomId);
    removeKey(END_STATE_PREFIX + roomId);
    getChannel(roomId)?.postMessage({ type: "clear" });
  }

  // ---- 대화 종료 상태 ----
  // status: "active"(대화 중) | "pending"(한쪽이 종료 요청) | "ended"(둘 다 동의)
  // requestedBy: 종료를 요청한 역할, declinedBy: 마지막으로 거절한 역할
  const DEFAULT_END_STATE = { status: "active", requestedBy: null, declinedBy: null };

  function loadEndState(roomId) {
    return { ...DEFAULT_END_STATE, ...readJson(END_STATE_PREFIX + roomId, {}) };
  }

  function saveEndState(roomId, state) {
    const next = { ...state, updatedAt: Date.now() };
    writeJson(END_STATE_PREFIX + roomId, next);
    getChannel(roomId)?.postMessage({ type: "end-state", state: next });
    return next;
  }

  function requestEnd(roomId, role) {
    const current = loadEndState(roomId);
    if (current.status !== "active") return current;
    return saveEndState(roomId, { status: "pending", requestedBy: role, declinedBy: null });
  }

  function respondEnd(roomId, role, agree) {
    const current = loadEndState(roomId);
    // 요청 중이 아니거나, 요청한 사람이 스스로 응답하는 경우는 무시
    if (current.status !== "pending" || current.requestedBy === role) return current;
    return saveEndState(
      roomId,
      agree
        ? { status: "ended", requestedBy: current.requestedBy, declinedBy: null }
        : { status: "active", requestedBy: null, declinedBy: role }
    );
  }

  // ---- 신고 ----
  function saveReport(report) {
    const saved = { id: createId(), ...report, createdAt: Date.now() };
    writeJson(REPORTS_KEY, [...readJson(REPORTS_KEY, []), saved]);
    return saved;
  }

  // 선배의 받은 대화 목록. roomPrefix로 시작하는 방 중 메시지가 있는 방을 최근순으로
  function listRooms(roomPrefix) {
    const keyPrefix = STORAGE_PREFIX + roomPrefix;
    let keys = [];
    try {
      keys = Object.keys(localStorage).filter((key) => key.startsWith(keyPrefix));
    } catch {
      return [];
    }
    return keys
      .map((key) => {
        const roomId = key.slice(STORAGE_PREFIX.length);
        const messages = loadMessages(roomId);
        const last = messages[messages.length - 1];
        return (
          last && {
            juniorId: roomId.slice(roomPrefix.length),
            lastMessage: last.text,
            lastAt: last.sentAt,
            status: loadEndState(roomId).status,
            messageCount: messages.length,
          }
        );
      })
      .filter(Boolean)
      .sort((a, b) => b.lastAt - a.lastAt);
  }

  // 상대 탭에서 온 새 메시지/초기화/종료 상태를 받음. 구독 해제 함수를 돌려줌
  function subscribe(roomId, { onMessage, onClear, onEndState }) {
    const channel = getChannel(roomId);
    if (!channel) return () => {};

    const listener = (e) => {
      if (e.data?.type === "message") onMessage?.(e.data.message);
      else if (e.data?.type === "clear") onClear?.();
      else if (e.data?.type === "end-state") onEndState?.(e.data.state);
    };
    channel.addEventListener("message", listener);
    return () => channel.removeEventListener("message", listener);
  }

  return {
    loadMessages,
    sendMessage,
    clearMessages,
    loadEndState,
    requestEnd,
    respondEnd,
    saveReport,
    listRooms,
    subscribe,
  };
})();
