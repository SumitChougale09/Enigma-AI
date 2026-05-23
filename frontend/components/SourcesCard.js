"use client";

import styles from "./SourcesCard.module.css";

export default function SourcesCard({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
        <span>Sources</span>
        <span className={styles.count}>{sources.length}</span>
      </div>
      <div className={styles.list}>
        {sources.map((src, i) => {
          let domain = "";
          try {
            domain = new URL(src.url).hostname.replace("www.", "");
          } catch {
            domain = src.url;
          }
          return (
            <a
              key={i}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.source}
              title={src.title}
            >
              <div className={styles.sourceIndex}>{src.index || i + 1}</div>
              <div className={styles.sourceInfo}>
                <span className={styles.sourceTitle}>{src.title}</span>
                <span className={styles.sourceDomain}>{domain}</span>
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}
