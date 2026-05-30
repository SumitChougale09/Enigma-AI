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

export async function deleteChat(token, chatId) {
  const res = await authFetch(
    `/chats/${chatId}`,
    { method: "DELETE" },
    token
  );
  return res.json();
}

export async function renameChat(token, chatId, title) {
  const res = await authFetch(
    `/chats/${chatId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    },
    token
  );
  return res.json();
}

// ─── Streaming Search (Authenticated SSE) ────────────────────

/**
 * Stream a search query via SSE with authentication and chat context.
 * The backend handles ALL message persistence — the frontend does NOT
 * need to separately call postMessage after streaming.
 *
 * @param {string} query - The search query
 * @param {function} onEvent - Callback for each SSE event: { eventType, ...data }
 * @param {object} options
 * @param {string} options.token - Supabase JWT for authenticated requests
 * @param {string|null} options.chatId - Existing chat ID to continue conversation
 * @param {AbortSignal} options.signal - AbortController signal to cancel the stream
 * @returns {Promise<void>}
 */
export async function streamSearch(query, onEvent, { token, chatId, signal } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ query, max_results: 5, chat_id: chatId || null }),
    signal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Stream error: ${res.status}`);
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
