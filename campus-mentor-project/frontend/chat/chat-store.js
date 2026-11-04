// 서버 없이 쓰는 가짜(목) 메시지 저장소. api.js에서 USE_MOCK=true일 때만 사용.
// localStorage(저장) + BroadcastChannel(같은 브라우저의 다른 탭으로 실시간 전달)
const ChatStore = (() => {
  const STORAGE_PREFIX = "campus-mentor-chat:";
  const channels = {};

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
    try {
      return JSON.parse(localStorage.getItem(STORAGE_PREFIX + roomId)) || [];
    } catch {
      return [];
    }
  }

  function saveMessages(roomId, messages) {
    try {
      localStorage.setItem(STORAGE_PREFIX + roomId, JSON.stringify(messages));
    } catch {
      // 저장소를 못 쓰는 환경(사생활 보호 모드 등)에서는 실시간 전달만 동작
    }
  }

  // 메시지를 저장하고 상대 탭에 전달한 뒤, 만들어진 메시지를 돌려줌
  function sendMessage(roomId, { role, text }) {
    const message = { id: createId(), role, text, sentAt: Date.now() };
    saveMessages(roomId, [...loadMessages(roomId), message]);
    getChannel(roomId)?.postMessage({ type: "message", message });
    return message;
  }

  function clearMessages(roomId) {
    try {
      localStorage.removeItem(STORAGE_PREFIX + roomId);
    } catch {
      // 무시
    }
    getChannel(roomId)?.postMessage({ type: "clear" });
  }

  // 상대 탭에서 온 새 메시지/초기화를 받음. 구독 해제 함수를 돌려줌
  function subscribe(roomId, { onMessage, onClear }) {
    const channel = getChannel(roomId);
    if (!channel) return () => {};

    const listener = (e) => {
      if (e.data?.type === "message") onMessage?.(e.data.message);
      else if (e.data?.type === "clear") onClear?.();
    };
    channel.addEventListener("message", listener);
    return () => channel.removeEventListener("message", listener);
  }

  return { loadMessages, sendMessage, clearMessages, subscribe };
})();
