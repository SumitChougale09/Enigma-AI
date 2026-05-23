/**
 * Backend API helpers for authenticated requests.
 * All chat/search endpoints go through the FastAPI backend on port 8000.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Make an authenticated fetch to the backend.
 */
async function authFetch(path, options = {}, token) {
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }

  return res;
}

// ─── Auth ────────────────────────────────────────────────────

export async function fetchMe(token) {
  const res = await authFetch("/auth/me", {}, token);
  return res.json();
}

// ─── Chats ───────────────────────────────────────────────────

export async function fetchChats(token) {
  const res = await authFetch("/chats", {}, token);
  return res.json();
}

export async function createChat(token, title) {
  const res = await authFetch(
    "/chats",
    {
      method: "POST",
      body: JSON.stringify({ title: title || null }),
    },
    token
  );
  return res.json();
}

export async function fetchChatMessages(token, chatId) {
  const res = await authFetch(`/chats/${chatId}/messages`, {}, token);
  return res.json();
}

export async function postMessage(token, chatId, role, content) {
  const res = await authFetch(
    `/chats/${chatId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ role, content }),
    },
    token
  );
  return res.json();
}

// ─── Streaming Search ────────────────────────────────────────

/**
 * Stream a search query via SSE.
 * Calls the /stream endpoint and yields parsed SSE events.
 *
 * @param {string} query - The search query
 * @param {function} onEvent - Callback for each SSE event: { type, ...data }
 * @returns {Promise<void>}
 */
export async function streamSearch(query, onEvent) {
  const res = await fetch(`${API_URL}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, max_results: 5 }),
  });

  if (!res.ok) {
    throw new Error(`Stream error: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const lines = buffer.split("\n");
    buffer = lines.pop() || ""; // Keep incomplete line in buffer

    let eventType = null;
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ") && eventType) {
        try {
          const data = JSON.parse(line.slice(6));
          onEvent({ eventType, ...data });
        } catch {
          // Skip malformed JSON
        }
        eventType = null;
      }
    }
  }
}
