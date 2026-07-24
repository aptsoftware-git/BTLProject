import React, { useCallback, useRef, useState } from "react";
import { uploadDocument } from "../api";

export default function UploadZone({ onUploaded }) {
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(null); // null = idle, 0-100 = uploading
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  const [lastFile, setLastFile] = useState(null); // Save last file to support retry

  const inputRef = useRef(null);
  const xhrRef = useRef(null); // Keep XHR reference to support cancellation

  const handleFiles = useCallback(
    async (files) => {
      const file = files?.[0];
      if (!file) return;

      setLastFile(file);
      setError(null);
      setSuccess(null);
      setProgress(0);

      try {
        const result = await uploadDocument(file, setProgress, xhrRef);
        setSuccess(`Document "${file.name}" uploaded successfully — proofreading started!`);
        onUploaded?.(result);
      } catch (err) {
        setError(err.message || "Upload failed. Please try again.");
      } finally {
        setProgress(null);
        xhrRef.current = null;
      }
    },
    [onUploaded]
  );

  const handleCancel = () => {
    if (xhrRef.current) {
      xhrRef.current.abort();
    }
  };

  const handleRetry = () => {
    if (lastFile) {
      handleFiles([lastFile]);
    }
  };

  return (
    <div style={styles.container}>
      <div
        style={{ ...styles.zone, ...(isDragging ? styles.zoneActive : {}) }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          style={{ display: "none" }}
          onChange={(e) => handleFiles(e.target.files)}
        />

        <div style={styles.iconCircle}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3v12" />
            <path d="M7 8l5-5 5 5" />
            <path d="M4 21h16" />
          </svg>
        </div>

        {progress !== null ? (
          <div style={styles.progressContainer}>
            <p style={styles.heading}>Uploading: {progress}%</p>
            <div style={styles.progressTrack}>
              <div style={{ ...styles.progressBar, width: `${progress}%` }} />
            </div>
            <button style={styles.cancelBtn} onClick={handleCancel}>
              Cancel Upload
            </button>
          </div>
        ) : (
          <>
            <p style={styles.heading}>Upload a document for AI review</p>
            <button style={styles.browseLink} onClick={() => inputRef.current?.click()}>
              Drag and drop your file here or click to browse
            </button>
          </>
        )}

        <p style={styles.hint}>Supports PDF, DOCX, and TXT up to 50MB</p>
      </div>

      {success && (
        <div style={styles.successBanner}>
          <span>{success}</span>
          <button style={styles.closeBtn} onClick={() => setSuccess(null)} aria-label="Dismiss">✕</button>
        </div>
      )}

      {error && (
        <div style={styles.errorBanner}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span>{error}</span>
            {lastFile && (
              <button style={styles.retryLink} onClick={handleRetry}>
                Try again
              </button>
            )}
          </div>
          <button style={styles.closeBtn} onClick={() => setError(null)} aria-label="Dismiss">✕</button>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { display: "flex", flexDirection: "column", gap: 12 },
  zone: {
    border: "2px dashed #D8D3F7",
    background: "var(--brand-light)",
    borderRadius: "var(--radius-lg)",
    padding: "20px 16px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
    transition: "border-color 0.15s, transform 0.2s",
    cursor: "pointer",
  },
  zoneActive: { borderColor: "var(--brand)" },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: "50%",
    background: "#E1DDFA",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  heading: { margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text-primary)" },
  browseLink: {
    background: "none", border: "none", color: "var(--brand)",
    fontSize: 13, fontWeight: 600, marginTop: 4, padding: 0,
    cursor: "pointer",
  },
  hint: { margin: "10px 0 0", fontSize: 11.5, color: "var(--text-muted)" },
  progressContainer: { width: "100%", maxWidth: 260, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 },
  progressTrack: { width: "100%", height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" },
  progressBar: { height: "100%", background: "var(--brand)", transition: "width 0.1s ease" },
  cancelBtn: {
    background: "none", border: "none", color: "var(--red)", fontSize: 11.5, fontWeight: 600, cursor: "pointer", padding: 0, marginTop: 4
  },
  successBanner: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    fontSize: 12.5, color: "var(--green)", background: "var(--green-light)",
    padding: "10px 16px", borderRadius: 8, border: "1px solid rgba(34, 197, 94, 0.15)",
    textAlign: "left",
  },
  errorBanner: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    fontSize: 12.5, color: "var(--red)", background: "var(--red-light)",
    padding: "10px 16px", borderRadius: 8, border: "1px solid rgba(225, 85, 85, 0.15)",
    textAlign: "left",
  },
  closeBtn: {
    background: "none", border: "none", color: "inherit",
    fontSize: 12, fontWeight: "bold", cursor: "pointer", paddingLeft: 12,
  },
  retryLink: {
    background: "none", border: "none", color: "var(--red)", fontSize: 11.5, fontWeight: 700,
    cursor: "pointer", padding: 0, textAlign: "left", textDecoration: "underline"
  }
};
