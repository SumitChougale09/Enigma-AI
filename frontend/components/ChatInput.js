"use client";

import { useRef, useEffect } from "react";
import styles from "./ChatInput.module.css";

export default function ChatInput({
  value,
  onChange,
  onSubmit,
  onStop,
  disabled,
  isStreaming,
  placeholder,
}) {
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [value]);

  // Focus textarea on mount and when streaming ends
  useEffect(() => {
    if (!isStreaming && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isStreaming]);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) {
        onSubmit();
      }
    }
  }

  return (
    <div className={styles.inputArea}>
      <div className={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Ask anything..."}
          rows={1}
          disabled={disabled}
        />
        {isStreaming ? (
          <button
            className={styles.stopBtn}
            onClick={onStop}
            title="Stop generating"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            className={styles.submitBtn}
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            title="Search"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
          </button>
        )}
      </div>
      <p className={styles.disclaimer}>
        ARIA searches the web and generates answers with AI. Always verify important information.
      </p>
    </div>
  );
}
