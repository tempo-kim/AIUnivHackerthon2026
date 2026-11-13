const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch (e) {}
    throw new Error(detail || `요청 실패 (${response.status})`);
  }

  return response.json();
}

const MentorApi = {
  health: () => apiRequest("/health"),
  listMentors: () => apiRequest("/api/mentors"),

  extract: (concernText) =>
    apiRequest("/api/extract", {
      method: "POST",
      body: JSON.stringify({ concern_text: concernText, use_llm: true }),
    }),

  match: (body) =>
    apiRequest("/api/match", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** 학교 생활 챗봇 — 매칭과 같은 LLM 키를 서버에서 사용 */
  schoolBot: (body) =>
    apiRequest("/api/school-bot", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
