"use client";

import SourcesCard from "./SourcesCard";
import styles from "./MessageBubble.module.css";

/**
 * Render a message with basic markdown-like formatting.
 * Supports: **bold**, headers, lists, code blocks, inline code.
 */
function renderContent(text) {
  if (!text) return null;

  // Split into lines and process
  const lines = text.split("\n");
  const elements = [];
  let inCodeBlock = false;
  let codeBuffer = [];
  let codeLang = "";

  lines.forEach((line, i) => {
    // Code block toggle
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <pre key={`code-${i}`} className={styles.codeBlock}>
            <code>{codeBuffer.join("\n")}</code>
          </pre>
        );
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = line.trim().slice(3);
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    // Headers
    if (line.startsWith("### ")) {
      elements.push(<h3 key={i}>{formatInline(line.slice(4))}</h3>);
      return;
    }
    if (line.startsWith("## ")) {
      elements.push(<h2 key={i}>{formatInline(line.slice(3))}</h2>);
      return;
    }
    if (line.startsWith("# ")) {
      elements.push(<h1 key={i}>{formatInline(line.slice(2))}</h1>);
      return;
    }

    // List items
    if (line.match(/^[-*•]\s/)) {
      elements.push(
        <li key={i}>{formatInline(line.replace(/^[-*•]\s/, ""))}</li>
      );
      return;
    }
    if (line.match(/^\d+\.\s/)) {
      elements.push(
        <li key={i}>{formatInline(line.replace(/^\d+\.\s/, ""))}</li>
      );
      return;
    }

    // Empty line
    if (line.trim() === "") {
      elements.push(<br key={i} />);
      return;
    }

    // Regular paragraph
    elements.push(<p key={i}>{formatInline(line)}</p>);
  });

  return elements;
}

/**
 * Process inline formatting: **bold**, `code`, [n] citation refs
 */
function formatInline(text) {
  if (!text) return text;

  const parts = [];
  let remaining = text;
  let keyIdx = 0;

  while (remaining.length > 0) {
    // Bold
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
    // Inline code
    const codeMatch = remaining.match(/`(.+?)`/);
    // Citation [n]
    const citeMatch = remaining.match(/\[(\d+)\]/);

    // Find earliest match
    let earliest = null;
    let matchType = null;

    if (boldMatch && (!earliest || boldMatch.index < earliest.index)) {
      earliest = boldMatch;
      matchType = "bold";
    }
    if (codeMatch && (!earliest || codeMatch.index < earliest.index)) {
      earliest = codeMatch;
      matchType = "code";
    }
    if (citeMatch && (!earliest || citeMatch.index < earliest.index)) {
      earliest = citeMatch;
      matchType = "cite";
    }

    if (!earliest) {
      parts.push(remaining);
      break;
    }

    // Add text before match
    if (earliest.index > 0) {
      parts.push(remaining.slice(0, earliest.index));
    }

    if (matchType === "bold") {
      parts.push(<strong key={keyIdx++}>{earliest[1]}</strong>);
    } else if (matchType === "code") {
      parts.push(<code key={keyIdx++} className={styles.inlineCode}>{earliest[1]}</code>);
    } else if (matchType === "cite") {
      parts.push(
        <sup key={keyIdx++} className={styles.citation}>{earliest[1]}</sup>
      );
    }

    remaining = remaining.slice(earliest.index + earliest[0].length);
  }

  return parts;
}

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const isError = message.isError;

  return (
    <div className={`${styles.message} ${isUser ? styles.userMessage : styles.assistantMessage} animate-fade-in`}>
      {!isUser && (
        <div className={`${styles.assistantIcon} ${isError ? styles.errorIcon : ""}`}>
          {isError ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="url(#msg-lg)" strokeWidth="2" />
              <path d="M10 20L16 10L22 20" stroke="url(#msg-lg)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="16" cy="14" r="2" fill="url(#msg-lg)" />
              <defs>
                <linearGradient id="msg-lg" x1="0" y1="0" x2="32" y2="32">
                  <stop stopColor="#20B2AA" />
                  <stop offset="1" stopColor="#5B8DEF" />
                </linearGradient>
              </defs>
            </svg>
          )}
        </div>
      )}

      <div className={styles.bubble}>
        {/* Sources (only for assistant messages) */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourcesCard sources={message.sources} />
        )}

        {/* Status indicator */}
        {message.status && (
          <div className={styles.status}>
            <span className={styles.statusDot} />
            {message.status}
          </div>
        )}

        {/* Content */}
        {message.content && (
          <div className={`${styles.content} ${isError ? styles.errorContent : ""} markdown-content`}>
            {renderContent(message.content)}
          </div>
        )}

        {/* Streaming cursor */}
        {message.streaming && message.content && (
          <span className={styles.streamCursor} />
        )}

        {/* Streaming indicator (when no content yet) */}
        {message.streaming && !message.content && !message.status && (
          <div className={styles.typingDots}>
            <span />
            <span />
            <span />
          </div>
        )}
      </div>
    </div>
  );
}
