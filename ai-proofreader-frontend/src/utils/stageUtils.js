/**
 * stageUtils.js
 * Single source of truth for Pipeline Stage Definitions, Executive Business Mapping,
 * and Technical AI Terminology Translation.
 */

export const BUSINESS_STAGES = [
  {
    num: 1,
    id: "stage_1_upload",
    name: "Document Uploaded",
    legacyName: "Upload Complete",
    description: "Document successfully received and queued.",
    flag: "upload_ready"
  },
  {
    num: 2,
    id: "stage_2_extraction",
    name: "Document Content Extraction",
    legacyName: "Document Extraction",
    description: "Extracting text, tables, images and document structure.",
    flag: "document_viewer_ready"
  },
  {
    num: 3,
    id: "stage_3_spell",
    name: "Language & Spelling Review",
    legacyName: "Spell Checking",
    description: "Identifying spelling and language issues.",
    flag: "spell_ready"
  },
  {
    num: 4,
    id: "stage_4_grammar",
    name: "Grammar & Writing Quality Review",
    legacyName: "Grammar Checking",
    description: "Analyzing grammar, readability and writing quality.",
    flag: "grammar_ready"
  },
  {
    num: 5,
    id: "stage_5_rag",
    name: "Knowledge Index Creation",
    legacyName: "RAG Index Construction",
    description: "Preparing document knowledge base for AI Q&A.",
    flag: "rag_ready"
  },
  {
    num: 6,
    id: "stage_6_context",
    name: "Consistency & Contradiction Review",
    legacyName: "Contextual Consistency Analysis",
    description: "Checking document consistency and detecting conflicts.",
    flag: "context_analysis_ready"
  },
  {
    num: 7,
    id: "stage_7_comparative",
    name: "Competitive Benchmark Analysis",
    legacyName: "Comparative Analysis",
    description: "Comparing document against industry and peer references.",
    flag: "comparative_analysis_ready"
  },
  {
    num: 8,
    id: "stage_8_reports",
    name: "Executive Insights Report",
    legacyName: "Executive Report Generation",
    description: "Generating management-ready executive insights.",
    flag: "reports_ready"
  }
];

/**
 * Translates raw technical backend AI status strings into clean business-friendly terminology.
 */
export function translateTechnicalStatus(rawStatus) {
  if (!rawStatus || typeof rawStatus !== "string") {
    return "Processing Document";
  }

  const s = rawStatus.trim().toLowerCase();

  if (s.includes("embedding") || s.includes("vector")) {
    return "Building Knowledge Index";
  }
  if (s.includes("grammar") || s.includes("writing quality")) {
    return "Reviewing Grammar & Writing Quality";
  }
  if (s.includes("spell") || s.includes("language")) {
    return "Reviewing Language & Spelling";
  }
  if (s.includes("context") || s.includes("consistency") || s.includes("ambiguity")) {
    return "Reviewing Document Consistency";
  }
  if (s.includes("comparative") || s.includes("benchmark") || s.includes("tavily") || s.includes("competitor")) {
    return "Performing Competitive Benchmarking";
  }
  if (s.includes("report") || s.includes("executive")) {
    return "Preparing Executive Insights Report";
  }
  if (s.includes("extract") || s.includes("docling") || s.includes("batch")) {
    return "Extracting Document Content";
  }
  if (s.includes("chunk")) {
    return "Structuring Document Content";
  }
  if (s.includes("claude") || s.includes("verification")) {
    return "Executing Multi-Agent Quality Audit";
  }

  // Remove technical words if any remain
  return rawStatus
    .replace(/RAG/gi, "Knowledge Base")
    .replace(/Vector Store/gi, "Knowledge Index")
    .replace(/Embeddings/gi, "Knowledge Index")
    .replace(/Chunking/gi, "Structuring")
    .replace(/Inference/gi, "Analysis")
    .replace(/Agent/gi, "Review");
}
