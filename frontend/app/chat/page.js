"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  fetchMe,
  fetchChats,
  createChat,
  fetchChatMessages,
  postMessage,
  streamSearch,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ChatInput from "@/components/ChatInput";
import MessageBubble from "@/components/MessageBubble";
import styles from "./chat.module.css";

const SUGGESTIONS = [
  "What is inference engineering?",
  "Latest AI breakthroughs 2026",
  "How does RAG work?",
  "Explain transformer architecture",
];

export default function ChatPage() {
  const router = useRouter();
  const messagesEndRef = useRef(null);

  // Auth state
  const [session, setSession] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Chat state
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [searching, setSearching] = useState(false);

  // ─── Auth Check ────────────────────────────────────────────
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      if (!s) {
        router.replace("/login");
        return;
      }
      setSession(s);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      if (!s) router.replace("/login");
    });

    return () => subscription.unsubscribe();
  }, [router]);

  // ─── Load User Profile + Chats ─────────────────────────────
  useEffect(() => {
    if (!session) return;

    async function init() {
      try {
        const token = session.access_token;
        const [me, chatList] = await Promise.all([
          fetchMe(token),
          fetchChats(token),
        ]);
        setUser(me);
        setChats(chatList);
      } catch (err) {
        console.error("Init error:", err);
      } finally {
        setLoading(false);
      }
    }

    init();
  }, [session]);

  // ─── Load Chat Messages ────────────────────────────────────
  useEffect(() => {
    if (!session || !activeChatId) return;

    async function loadMessages() {
      try {
        const msgs = await fetchChatMessages(session.access_token, activeChatId);
        setMessages(msgs.map((m) => ({ ...m, role: m.role, content: m.content })));
      } catch (err) {
        console.error("Load messages error:", err);
      }
    }

    loadMessages();
  }, [session, activeChatId]);

  // ─── Auto-scroll ───────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ─── Handlers ──────────────────────────────────────────────

  const handleNewChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
    setInput("");
  }, []);

  const handleSelectChat = useCallback((chatId) => {
    setActiveChatId(chatId);
    setMessages([]);
  }, []);

  const handleLogout = useCallback(async () => {
    await supabase.auth.signOut();
    router.replace("/login");
  }, [router]);

  const handleSearch = useCallback(async () => {
    const query = input.trim();
    if (!query || !session || searching) return;

    setInput("");
    setSearching(true);

    // Add user message
    const userMsg = { role: "user", content: query, id: `temp-user-${Date.now()}` };

    // Add streaming assistant placeholder
    const assistantId = `temp-assistant-${Date.now()}`;
    const assistantMsg = {
      role: "assistant",
      content: "",
      sources: [],
      status: "Searching the web...",
      streaming: true,
      id: assistantId,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    try {
      const token = session.access_token;

      // Create or use existing chat
      let chatId = activeChatId;
      if (!chatId) {
        const chat = await createChat(token, query.slice(0, 80));
        chatId = chat.id;
        setActiveChatId(chatId);
        setChats((prev) => [chat, ...prev]);
      }

      // Save user message to DB
      await postMessage(token, chatId, "user", query);

      // Stream search
      let fullAnswer = "";
      let sources = [];

      await streamSearch(query, (event) => {
        if (event.eventType === "status") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, status: event.message } : m
            )
          );
        } else if (event.eventType === "sources") {
          sources = event.sources || [];
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources, status: "" } : m
            )
          );
        } else if (event.eventType === "token") {
          fullAnswer += event.content;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: fullAnswer } : m
            )
          );
        } else if (event.eventType === "done") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: event.full_answer, streaming: false, status: "" }
                : m
            )
          );
        } else if (event.eventType === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: `Error: ${event.message}`,
                    streaming: false,
                    status: "",
                  }
                : m
            )
          );
        }
      });

      // Save assistant message to DB
      if (fullAnswer) {
        await postMessage(token, chatId, "assistant", fullAnswer);
      }

      // Refresh chat list (title may have changed)
      const updatedChats = await fetchChats(token);
      setChats(updatedChats);
    } catch (err) {
      console.error("Search error:", err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: `Error: ${err.message}`,
                streaming: false,
                status: "",
              }
            : m
        )
      );
    } finally {
      setSearching(false);
    }
  }, [input, session, searching, activeChatId]);

  // ─── Loading State ─────────────────────────────────────────
  if (loading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.loadingSpinner} />
        <p>Loading ARIA...</p>
      </div>
    );
  }

  const showEmpty = !activeChatId && messages.length === 0;

  return (
    <div className={styles.appLayout}>
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        user={user}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onLogout={handleLogout}
      />

      <div className={styles.mainContent}>
        {showEmpty ? (
          /* ─── Empty State ──────────────────────── */
          <div className={styles.emptyState}>
            <div className={styles.emptyInner}>
              <div className={styles.emptyLogo}>
                <svg width="48" height="48" viewBox="0 0 32 32" fill="none">
                  <circle cx="16" cy="16" r="14" stroke="url(#el-lg)" strokeWidth="2" />
                  <path d="M10 20L16 10L22 20" stroke="url(#el-lg)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <circle cx="16" cy="14" r="2" fill="url(#el-lg)" />
                  <defs>
                    <linearGradient id="el-lg" x1="0" y1="0" x2="32" y2="32">
                      <stop stopColor="#20B2AA" />
                      <stop offset="1" stopColor="#5B8DEF" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              <h2 className={styles.emptyTitle}>What do you want to know?</h2>
              <p className={styles.emptySubtitle}>
                Search the web with AI-powered answers and citations
              </p>

              <div className={styles.chips}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    className={styles.chip}
                    onClick={() => {
                      setInput(s);
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* ─── Messages ─────────────────────────── */
          <div className={styles.messagesContainer}>
            <div className={styles.messagesList}>
              {messages.map((msg, i) => (
                <MessageBubble key={msg.id || i} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* ─── Input Bar ───────────────────────────── */}
        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={handleSearch}
          disabled={searching}
        />
      </div>
    </div>
  );
}
