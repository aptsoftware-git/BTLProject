import React, { useEffect, useMemo, useState } from "react";
import { fetchDocumentImages } from "../api";
import { resolveImageUrl } from "./Assistant";

// Every card in this gallery is sourced directly from the backend's
// /documents/{id}/images endpoint, which only ever lists strict
// image_XXX.png <-> image_XXX.json pairs from 05_images/ -- no chat
// top_k limits, no raw/temp extraction artefacts.
export default function ImageGallery({ docId }) {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchDocumentImages(docId)
      .then((res) => {
        if (cancelled) return;
        setImages(Array.isArray(res?.images) ? res.images : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || "Failed to load document images.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [docId]);

  const imageTypes = useMemo(() => {
    const types = new Set(images.map((img) => img.image_type).filter(Boolean));
    return ["all", ...Array.from(types).sort()];
  }, [images]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return images.filter((img) => {
      if (typeFilter !== "all" && img.image_type !== typeFilter) return false;
      if (!q) return true;
      const haystack = [
        img.image_id, img.entity_name, img.designation, img.caption,
        img.semantic_description, ...(img.keywords || []),
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(q);
    });
  }, [images, typeFilter, search]);

  const retrievableCount = images.filter((img) => img.retrievable).length;

  if (loading) {
    return <div style={styles.stateBox}>Loading extracted images…</div>;
  }
  if (error) {
    return <div style={{ ...styles.stateBox, color: "var(--red, #dc2626)" }}>{error}</div>;
  }
  if (images.length === 0) {
    return <div style={styles.stateBox}>No extracted images found for this document.</div>;
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>Extracted Images</h2>
          <p style={styles.subtitle}>
            {images.length} total asset{images.length === 1 ? "" : "s"} from 05_images
            {" · "}
            {retrievableCount} retrievable in AI Assistant searches
          </p>
        </div>
        <div style={styles.controls}>
          <input
            type="text"
            placeholder="Search caption, description, entity, keyword…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={styles.searchInput}
          />
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={styles.select}>
            {imageTypes.map((t) => (
              <option key={t} value={t}>{t === "all" ? "All types" : t}</option>
            ))}
          </select>
        </div>
      </div>

      <p style={styles.resultCount}>{filtered.length} of {images.length} shown</p>

      <div style={styles.grid}>
        {filtered.map((img) => {
          const src = resolveImageUrl(img.image_url || img.image_path || "");
          const isExpanded = expandedId === img.image_id;
          return (
            <div key={img.image_id || img.image_path} style={styles.card}>
              <a href={src} target="_blank" rel="noopener noreferrer" style={styles.thumbLink} title="Open full-size image">
                {src ? (
                  <img src={src} alt={img.caption || img.image_type || "Extracted image"} style={styles.thumb} />
                ) : (
                  <div style={styles.thumbMissing}>No preview</div>
                )}
              </a>

              <div style={styles.cardBody}>
                <div style={styles.badgeRow}>
                  <span style={styles.typeBadge}>{img.image_type || "Image"}</span>
                  <span style={{
                    ...styles.retrievableBadge,
                    ...(img.retrievable ? styles.retrievableTrue : styles.retrievableFalse),
                  }}>
                    {img.retrievable ? "Retrievable" : "Not retrievable"}
                  </span>
                  <span style={styles.pageBadge}>Page {img.page ?? "—"}</span>
                </div>

                {img.entity_name && (
                  <div style={styles.entityLine}>
                    <strong>{img.entity_name}</strong>
                    {img.designation ? ` — ${img.designation}` : ""}
                  </div>
                )}

                {img.caption && <div style={styles.caption}>{img.caption}</div>}

                {img.semantic_description && (
                  <p style={styles.description}>
                    {isExpanded || img.semantic_description.length <= 140
                      ? img.semantic_description
                      : `${img.semantic_description.slice(0, 140)}…`}
                    {img.semantic_description.length > 140 && (
                      <button
                        style={styles.expandBtn}
                        onClick={() => setExpandedId(isExpanded ? null : img.image_id)}
                      >
                        {isExpanded ? "Show less" : "Show more"}
                      </button>
                    )}
                  </p>
                )}

                {img.keywords && img.keywords.length > 0 && (
                  <div style={styles.keywordRow}>
                    {img.keywords.slice(0, 6).map((kw, idx) => (
                      <span key={idx} style={styles.keywordChip}>{kw}</span>
                    ))}
                  </div>
                )}

                <div style={styles.idLine} title={img.image_id}>{img.image_id}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const styles = {
  wrapper: { display: "flex", flexDirection: "column", gap: 16, width: "100%" },
  stateBox: {
    padding: 40, textAlign: "center", color: "var(--text-secondary, #6b7280)",
    background: "var(--surface, #fff)", borderRadius: 12, border: "1px solid var(--border, #e5e7eb)",
  },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    flexWrap: "wrap", gap: 12,
  },
  title: { margin: 0, fontSize: 20, fontWeight: 700, color: "var(--text-primary, #111827)" },
  subtitle: { margin: "4px 0 0", fontSize: 13, color: "var(--text-secondary, #6b7280)" },
  controls: { display: "flex", gap: 8, flexWrap: "wrap" },
  searchInput: {
    padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border, #d1d5db)",
    fontSize: 13, minWidth: 260, background: "var(--surface, #fff)", color: "inherit",
  },
  select: {
    padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border, #d1d5db)",
    fontSize: 13, background: "var(--surface, #fff)", color: "inherit",
  },
  resultCount: { margin: 0, fontSize: 12, color: "var(--text-secondary, #6b7280)" },
  grid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16,
  },
  card: {
    border: "1px solid var(--border, #e5e7eb)", borderRadius: 12, overflow: "hidden",
    background: "var(--surface, #fff)", display: "flex", flexDirection: "column",
  },
  thumbLink: { display: "block", background: "var(--surface-alt, #f3f4f6)" },
  thumb: { width: "100%", height: 160, objectFit: "contain", display: "block" },
  thumbMissing: {
    width: "100%", height: 160, display: "flex", alignItems: "center", justifyContent: "center",
    color: "var(--text-secondary, #9ca3af)", fontSize: 12,
  },
  cardBody: { padding: 12, display: "flex", flexDirection: "column", gap: 6 },
  badgeRow: { display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" },
  typeBadge: {
    fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
    background: "var(--brand-light, #eff6ff)", color: "var(--brand, #2563eb)",
  },
  retrievableBadge: { fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999 },
  retrievableTrue: { background: "var(--green-light, #ecfdf5)", color: "var(--green, #059669)" },
  retrievableFalse: { background: "#fef2f2", color: "#dc2626" },
  pageBadge: { fontSize: 11, color: "var(--text-secondary, #6b7280)", marginLeft: "auto" },
  entityLine: { fontSize: 13, color: "var(--text-primary, #111827)" },
  caption: { fontSize: 13, fontWeight: 600, color: "var(--text-primary, #111827)" },
  description: { fontSize: 12, color: "var(--text-secondary, #6b7280)", margin: 0, lineHeight: 1.5 },
  expandBtn: {
    background: "none", border: "none", color: "var(--brand, #2563eb)", cursor: "pointer",
    fontSize: 12, padding: 0, marginLeft: 4, textDecoration: "underline",
  },
  keywordRow: { display: "flex", gap: 4, flexWrap: "wrap" },
  keywordChip: {
    fontSize: 10, padding: "2px 6px", borderRadius: 6,
    background: "var(--surface-alt, #f3f4f6)", color: "var(--text-secondary, #6b7280)",
  },
  idLine: {
    fontSize: 10, color: "var(--text-tertiary, #9ca3af)", marginTop: 4,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
};
