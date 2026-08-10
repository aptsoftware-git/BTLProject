import React, { useMemo } from "react";

/**
 * CorrectedPreviewPanel
 * -----------------------
 * Live corrected-document preview: recomputed entirely client-side from the
 * current findings' accept/reject state, so it updates instantly (no
 * round-trip) the moment a finding is accepted or rejected. Only sentences
 * touched by an accepted finding are shown with their before/after text.
 */
export default function CorrectedPreviewPanel({ findings = [], onExport, isExporting = false }) {
  const touchedSentences = useMemo(() => {
    const bySentence = new Map();
    for (const f of findings) {
      if (f.status !== "accepted" || !f.sentence_id || f.token_start === null || f.token_start === undefined) continue;
      if (!bySentence.has(f.sentence_id)) {
        bySentence.set(f.sentence_id, {
          sentence_id: f.sentence_id,
          page_number: f.page_number,
          original: f.sentence_text || "",
          findings: [],
        });
      }
      bySentence.get(f.sentence_id).findings.push(f);
    }

    const rows = [];
    for (const entry of bySentence.values()) {
      let corrected = entry.original;
      const sorted = [...entry.findings].sort((a, b) => b.token_start - a.token_start);
      for (const f of sorted) {
        if (f.token_start >= 0 && f.token_end <= corrected.length) {
          corrected = corrected.slice(0, f.token_start) + f.suggestion + corrected.slice(f.token_end);
        }
      }
      rows.push({ ...entry, corrected });
    }
    return rows.sort((a, b) => (a.page_number || 0) - (b.page_number || 0));
  }, [findings]);

  const acceptedCount = findings.filter((f) => f.status === "accepted").length;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px", background: "#f8fafc" }}>
      <div style={{ maxWidth: "800px", margin: "0 auto", background: "#ffffff", padding: "32px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid #e2e8f0", paddingBottom: "12px", marginBottom: "20px" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "17px", fontWeight: 800, color: "#0f172a" }}>Live Corrected Preview</h2>
            <span style={{ fontSize: "12px", color: "#64748b" }}>{acceptedCount} accepted correction(s) applied</span>
          </div>
          <div style={{ display: "flex", gap: "6px" }}>
            {["pdf", "docx", "html"].map((fmt) => (
              <button
                key={fmt}
                onClick={() => onExport && onExport(fmt)}
                disabled={isExporting}
                style={{ background: "#166534", color: "#fff", border: "none", borderRadius: "6px", padding: "8px 12px", fontSize: "11.5px", fontWeight: 700, cursor: "pointer" }}
              >
                {isExporting ? "Exporting…" : `Export .${fmt}`}
              </button>
            ))}
          </div>
        </div>

        {touchedSentences.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: "#94a3b8", fontSize: "13px" }}>
            No accepted corrections yet. Accept findings in the sentence review to see them here.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {touchedSentences.map((row) => (
              <div key={row.sentence_id} style={{ borderLeft: "3px solid #22c55e", paddingLeft: "12px" }}>
                <div style={{ fontSize: "10.5px", fontWeight: 700, color: "#94a3b8", marginBottom: "4px" }}>
                  Page {row.page_number} • {row.sentence_id}
                </div>
                <div style={{ fontSize: "13px", color: "#991b1b", textDecoration: "line-through", opacity: 0.6, marginBottom: "2px" }}>
                  {row.original}
                </div>
                <div style={{ fontSize: "14px", color: "#14532d", fontWeight: 600 }}>{row.corrected}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
