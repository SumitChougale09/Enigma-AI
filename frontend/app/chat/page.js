"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  fetchMe,
  fetchChats,
  createChat,
  fetchChatMessages,
  deleteChat,
  renameChat,
  streamSearch,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ChatInput from "@/components/ChatInput";
import MessageBubble from "@/components/MessageBubble";
import styles from "./chat.module.css";

const SUGGESTIONS = [
  "What is inference engineering?",
  "Latest AI breakthroughs 2025",
  "How does RAG work?",
  "Explain transformer architecture",
  "What is the current price of Bitcoin?",
  "Who won the last FIFA World Cup?",
];

export default function ChatPage() {
  const router = useRouter();
  const messagesEndRef = useRef(null);
  const abortRef = useRef(null);
  const messagesContainerRef = useRef(null);

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
    if (!session || !activeChatId) {
      if (!activeChatId) setMessages([]);
      return;
    }

    async function loadMessages() {
      try {
        const msgs = await fetchChatMessages(session.access_token, activeChatId);
        setMessages(
          msgs.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            created_at: m.created_at,
          }))
        );
      } catch (err) {
        console.error("Load messages error:", err);
      }
    }

    loadMessages();
  }, [session, activeChatId]);

  // ─── Auto-scroll (smarter: only if near bottom) ────────────
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    // Auto-scroll if user is near the bottom (within 150px)
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 150;
    if (isNearBottom) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  // ─── Handlers ──────────────────────────────────────────────

  const handleNewChat = useCallback(() => {
    // Cancel any ongoing stream
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setActiveChatId(null);
    setMessages([]);
    setInput("");
    setSearching(false);
  }, []);

  const handleSelectChat = useCallback(
    (chatId) => {
      if (chatId === activeChatId) return;
      // Cancel any ongoing stream
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setActiveChatId(chatId);
      setMessages([]);
      setSearching(false);
    },
    [activeChatId]
  );

  const handleDeleteChat = useCallback(
    async (chatId) => {
      if (!session) return;
      try {
        await deleteChat(session.access_token, chatId);
        setChats((prev) => prev.filter((c) => c.id !== chatId));
        if (activeChatId === chatId) {
          setActiveChatId(null);
          setMessages([]);
        }
      } catch (err) {
        console.error("Delete chat error:", err);
      }
    },
    [session, activeChatId]
  );

  const handleLogout = useCallback(async () => {
    await supabase.auth.signOut();
    router.replace("/login");
  }, [router]);

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setSearching(false);
      // Mark any streaming messages as done
      setMessages((prev) =>
        prev.map((m) =>
          m.streaming ? { ...m, streaming: false, status: "" } : m
        )
      );
    }
  }, []);

  const handleSearch = useCallback(
    async (queryOverride) => {
      const query = (queryOverride || input).trim();
      if (!query || !session || searching) return;

      setInput("");
      setSearching(true);

      // Create AbortController for this stream
      const controller = new AbortController();
      abortRef.current = controller;

      // Add user message
      const userMsg = {
        role: "user",
        content: query,
        id: `temp-user-${Date.now()}`,
      };

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

        // If no active chat, create one first via API
        let chatId = activeChatId;
        if (!chatId) {
          const chat = await createChat(token, query.slice(0, 80));
          chatId = chat.id;
          setActiveChatId(chatId);
          setChats((prev) => [chat, ...prev]);
        }

        // Stream search — backend handles ALL message persistence
        let fullAnswer = "";
        let streamChatId = chatId;

        await streamSearch(
          query,
          (event) => {
            if (event.eventType === "status") {
              // Track chat_id from the first status event
              if (event.chat_id) {
                streamChatId = event.chat_id;
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, status: event.message }
                    : m
                )
              );
            } else if (event.eventType === "sources") {
              const sources = event.sources || [];
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, sources, status: "" }
                    : m
                )
              );
            } else if (event.eventType === "token") {
              fullAnswer += event.content;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: fullAnswer }
                    : m
                )
              );
            } else if (event.eventType === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: event.full_answer,
                        streaming: false,
                        status: "",
                      }
                    : m
                )
              );
            } else if (event.eventType === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: `⚠️ ${event.message}`,
                        streaming: false,
                        status: "",
                        isError: true,
                      }
                    : m
                )
              );
            }
          },
          { token, chatId, signal: controller.signal }
        );

        // Refresh chat list (title may have updated server-side)
        const updatedChats = await fetchChats(token);
        setChats(updatedChats);
      } catch (err) {
        if (err.name === "AbortError") {
          // User cancelled — already handled in handleStop
          return;
        }
        console.error("Search error:", err);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: `⚠️ ${err.message}`,
                  streaming: false,
                  status: "",
                  isError: true,
                }
              : m
          )
        );
      } finally {
        setSearching(false);
        abortRef.current = null;
      }
    },
    [input, session, searching, activeChatId]
  );

  // ─── Loading State ─────────────────────────────────────────
  if (loading) {
    return (
      <div className={styles.loadingScreen}>
        <div className={styles.loadingLogo}>
          <svg width="48" height="48" viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" stroke="url(#ld-lg)" strokeWidth="2" />
            <path d="M10 20L16 10L22 20" stroke="url(#ld-lg)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="16" cy="14" r="2" fill="url(#ld-lg)" />
            <defs>
              <linearGradient id="ld-lg" x1="0" y1="0" x2="32" y2="32">
                <stop stopColor="#20B2AA" />
                <stop offset="1" stopColor="#5B8DEF" />
              </linearGradient>
            </defs>
          </svg>
        </div>
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
        onDeleteChat={handleDeleteChat}
        onLogout={handleLogout}
      />

      <div className={styles.mainContent}>
        {/* Header bar for active chat */}
        {activeChatId && (
          <div className={styles.chatHeader}>
            <h2 className={styles.chatTitle}>
              {chats.find((c) => c.id === activeChatId)?.title || "Chat"}
            </h2>
          </div>
        )}

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
                      // Auto-submit after a small delay so the input renders
                      setTimeout(() => handleSearch(s), 50);
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={styles.chipIcon}>
                      <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
                    </svg>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* ─── Messages ─────────────────────────── */
          <div className={styles.messagesContainer} ref={messagesContainerRef}>
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
          onStop={handleStop}
          disabled={searching}
          isStreaming={searching}
        />
      </div>
    </div>
  );
}
