// 백엔드 API 클라이언트 (매칭까지). 채팅 API는 추후.
// 서버와 같은 출처로 열면 API_BASE_URL을 "" 로 두면 됩니다.
// file:// 로 열 때는 "http://127.0.0.1:8000"
const API_BASE_URL = window.PPUN_API_BASE || (location.protocol === "file:" ? "http://127.0.0.1:8000" : "");

async function apiRequest(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      detail = err.detail ? `: ${typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail)}` : "";
    } catch (_) {}
    throw new Error(`요청 실패 (${res.status})${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

const MentorApi = {
  health: () => apiRequest("/health"),
  listMentors: () => apiRequest("/api/mentors"),
  match: (body) =>
    apiRequest("/api/match", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
