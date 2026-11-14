const BASE = "/api";

async function request(path, { method = "GET", body, signal } = {}) {
  const response = await fetch(BASE + path, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message =
      (data && (data.message || (data.detail && data.detail.message))) || `请求失败（${response.status}）`;
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    if (response.status === 401) {
      window.dispatchEvent(new Event("session-expired"));
    }
    throw error;
  }
  return data;
}

function query(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  me: () => request("/auth/me"),
  login: (password) => request("/auth/login", { method: "POST", body: { password } }),
  logout: () => request("/auth/logout", { method: "POST", body: {} }),

  health: () => request("/health"),

  today: () => request("/today"),
  settings: () => request("/settings"),
  saveSettings: (payload) => request("/settings", { method: "PUT", body: payload }),

  startCycle: () => request("/cycle/start", { method: "POST", body: {} }),
  currentCycle: () => request("/cycle/current"),
  cycleNext: (cycleId) => request(`/cycle/${cycleId}/next`),
  cycleAnswer: (cycleId, payload) => request(`/cycle/${cycleId}/answer`, { method: "POST", body: payload }),
  adjustAnswer: (cycleId, wordId, choice) =>
    request(`/cycle/${cycleId}/adjust`, { method: "POST", body: { wordId, choice } }),
  abandonCycle: (cycleId) => request(`/cycle/${cycleId}/abandon`, { method: "POST", body: {} }),
  cycleReviewCards: (cycleId) => request(`/cycle/${cycleId}/review-cards`),
  markCardRead: (cycleId, wordId) =>
    request(`/cycle/${cycleId}/cards/${wordId}/read`, { method: "POST", body: {} }),
  setMark: (id, mark) => request(`/words/${id}/mark`, { method: "PUT", body: { mark } }),

  words: (params) => request(`/words${query(params)}`),
  word: (id) => request(`/words/${id}`),
  createWord: (payload) => request("/words", { method: "POST", body: payload }),
  updateWord: (id, payload) => request(`/words/${id}`, { method: "PATCH", body: payload }),
  deleteWord: (id) => request(`/words/${id}`, { method: "DELETE" }),
  importWords: (text) => request("/words/import", { method: "POST", body: { text } }),
  exportUrl: (format = "json") => `${BASE}/words/export?format=${format}`,
  purgeWords: (confirm) => request("/words/purge", { method: "POST", body: { confirm } }),
  annotation: (id) => request(`/words/${id}/annotation`),
  saveAnnotation: (id, payload) => request(`/words/${id}/annotation`, { method: "PATCH", body: payload }),

  annotate: (wordIds) => request("/annotate", { method: "POST", body: { wordIds } }),
  importAnnotations: (items) => request("/annotate/import", { method: "POST", body: { items } }),
  annotateStatus: () => request("/annotate/status"),

  llmConfig: () => request("/llm-config"),
  saveLlmConfig: (payload) => request("/llm-config", { method: "PUT", body: payload }),
  testLlm: () => request("/llm-config/test", { method: "POST", body: {} }),

  roots: (params) => request(`/roots${query(params)}`),
  root: (id) => request(`/roots/${id}`),
  affixes: (params) => request(`/affixes${query(params)}`),
  affix: (id) => request(`/affixes/${id}`),

  stats: () => request("/stats"),
};
