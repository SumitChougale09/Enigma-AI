"use client";

import { useState } from "react";
import styles from "./Sidebar.module.css";

export default function Sidebar({
  chats,
  activeChatId,
  user,
  onNewChat,
  onSelectChat,
  onLogout,
}) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const filtered = chats.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  // Group chats by time
  const today = new Date();
  const groups = { Today: [], "Last 7 Days": [], Older: [] };
  filtered.forEach((chat) => {
    const d = new Date(chat.created_at);
    const diff = (today - d) / (1000 * 60 * 60 * 24);
    if (diff < 1) groups["Today"].push(chat);
    else if (diff < 7) groups["Last 7 Days"].push(chat);
    else groups["Older"].push(chat);
  });

  return (
    <>
      {/* Mobile toggle */}
      <button
        className={styles.mobileToggle}
        onClick={() => setCollapsed(!collapsed)}
        aria-label="Toggle sidebar"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      <aside className={`${styles.sidebar} ${collapsed ? styles.open : ""}`}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.brand}>
            <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="url(#sb-lg)" strokeWidth="2.5" />
              <path d="M10 20L16 10L22 20" stroke="url(#sb-lg)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="16" cy="14" r="2" fill="url(#sb-lg)" />
              <defs>
                <linearGradient id="sb-lg" x1="0" y1="0" x2="32" y2="32">
                  <stop stopColor="#20B2AA" />
                  <stop offset="1" stopColor="#5B8DEF" />
                </linearGradient>
              </defs>
            </svg>
            <span className={styles.brandName}>ARIA</span>
          </div>
          <button className={styles.newChatBtn} onClick={onNewChat} title="New Chat">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className={styles.searchBox}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            type="text"
            placeholder="Search chats..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Chat list */}
        <div className={styles.chatList}>
          {filtered.length === 0 && (
            <p className={styles.empty}>No chats yet. Start a new one!</p>
          )}

          {Object.entries(groups).map(
            ([label, items]) =>
              items.length > 0 && (
                <div key={label} className={styles.group}>
                  <p className={styles.groupLabel}>{label}</p>
                  {items.map((chat) => (
                    <button
                      key={chat.id}
                      className={`${styles.chatItem} ${chat.id === activeChatId ? styles.chatItemActive : ""}`}
                      onClick={() => {
                        onSelectChat(chat.id);
                        setCollapsed(false);
                      }}
                      title={chat.title}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={styles.chatIcon}>
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <span className={styles.chatTitle}>{chat.title}</span>
                    </button>
                  ))}
                </div>
              )
          )}
        </div>

        {/* User footer */}
        <div className={styles.footer}>
          <div className={styles.userInfo}>
            <div className={styles.avatar}>
              {user?.full_name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || "?"}
            </div>
            <div className={styles.userDetails}>
              <span className={styles.userName}>{user?.full_name || "User"}</span>
              <span className={styles.userEmail}>{user?.email || ""}</span>
            </div>
          </div>
          <button className={styles.logoutBtn} onClick={onLogout} title="Sign Out">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {collapsed && <div className={styles.overlay} onClick={() => setCollapsed(false)} />}
    </>
  );
}
