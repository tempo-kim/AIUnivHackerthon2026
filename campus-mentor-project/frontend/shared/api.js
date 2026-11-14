const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

/** 매칭 LLM(~15s) / 학교봇 LLM(~40s) 백엔드 제한과 맞춤 — 한쪽이 먼저 끊겨 다른 쪽만 되는 착시 방지 */
const MATCH_TIMEOUT_MS = 25000;
const SCHOOL_BOT_TIMEOUT_MS = 45000;

async function apiRequest(path, options = {}) {
  const timeoutMs = options.timeoutMs;
  const { timeoutMs: _ignored, signal: outerSignal, ...fetchOptions } = options;
  const controller = typeof timeoutMs === "number" ? new AbortController() : null;
  const timer =
    controller && timeoutMs
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      signal: controller ? controller.signal : outerSignal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchOptions.headers || {}),
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
  } finally {
    if (timer) clearTimeout(timer);
  }
}

const MentorApi = {
  health: () => apiRequest("/health"),
  listMentors: () => apiRequest("/api/mentors"),

  extract: (concernText) =>
    apiRequest("/api/extract", {
      method: "POST",
      body: JSON.stringify({ concern_text: concernText, use_llm: true }),
      timeoutMs: MATCH_TIMEOUT_MS,
    }),

  match: (body) =>
    apiRequest("/api/match", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: MATCH_TIMEOUT_MS,
    }),

  /** 학교 생활 챗봇 — 매칭과 같은 LLM 키를 서버에서 사용 */
  schoolBot: (body) =>
    apiRequest("/api/school-bot", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: SCHOOL_BOT_TIMEOUT_MS,
    }),

  schoolBot: (body) =>
    apiRequest("/api/school-bot", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
