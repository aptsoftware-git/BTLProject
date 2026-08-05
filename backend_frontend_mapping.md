# Backend-to-Frontend State Mapping Specification

## Overview
This document defines the exact mapping between backend data models, processing flags, pipeline stage states, and frontend UI components in the AI Document Intelligence Platform.

---

## 1. 8-Stage Pipeline Mapping Matrix

| Stage # | Backend Stage ID | Backend Stage Name (`STAGES_DEFINITIONS`) | Backend Readiness Flag | Frontend Display Name | Unlocked Workspace Feature / View |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | `stage_1_upload` | Document Uploaded | `upload_ready` | Document Uploaded | Document Metadata & Upload Status |
| **2** | `stage_2_extraction` | Document Content Extraction | `document_viewer_ready` / `extraction_ready` | Document Content Extraction | Document Viewer & Raw Text |
| **3** | `stage_3_spell` | Language & Spelling Review | `spell_ready` | Language & Spelling Review | Proofreading (Spelling Candidates) |
| **4** | `stage_4_grammar` | Grammar & Writing Quality Review | `grammar_ready` / `proofreading_ready` | Grammar & Writing Quality Review | Full Interactive Proofreading & Clean Preview |
| **5** | `stage_5_rag` | Knowledge Index Creation | `rag_ready` | Knowledge Index Creation | AI Document Assistant (Interactive Q&A) |
| **6** | `stage_6_context` | Consistency & Contradiction Review | `context_analysis_ready` | Consistency & Contradiction Review | Ambiguity Analysis & Conflict Mapping |
| **7** | `stage_7_comparative` | Competitive Benchmark Analysis | `comparative_analysis_ready` | Competitive Benchmark Analysis | Executive Comparative Analysis Dashboard |
| **8** | `stage_8_reports` | Executive Insights Report | `reports_ready` | Executive Insights Report | Management Reports & Multi-Format Exports |

---

## 2. Stage Status Enum Mapping

Backend stage status strings are transformed directly to frontend visual badges:

| Backend `st.status` | Frontend Badge State | Visual Styling | Indicator Component |
| :--- | :--- | :--- | :--- |
| `Pending` / `queued` | **Queued** | Gray border (`var(--border)`), Muted text | Static circular badge number |
| `Running` | **Running** | Brand Purple border (`var(--brand)`), Purple background tint | Animated CSS spinner + Circular badge |
| `Completed` / `Skipped` | **Completed** | Green border (`var(--green)`), Light green tint | Green checkmark (`✓`) |
| `Failed` | **Failed** | Red border (`var(--red)`), Light red tint | Red warning icon (`⚠`) + Error Trace + Retry Button |

---

## 3. Executive Card Data Binding

Each Executive Card on the Workspace Overview tab binds to specific backend output attributes:

### 1. Proofreading & Quality Card
- **Readiness Condition**: `doc.proofreading_ready || doc.spell_ready || doc.grammar_ready || doc.status === "completed"`
- **Count Metric**: `doc.issues.length`
- **Locked Display**: `"Stage 3/4 Processing..."`
- **Unlocked Display**: `${totalIssues} Issues Found` or `"Ready for Publication"`

### 2. Ambiguity Analysis Card
- **Readiness Condition**: `doc.context_analysis_ready || doc.context_analysis_status === "completed" || doc.status === "completed"`
- **Count Metric**: `doc.context_analysis_issues_count`
- **Locked Display**: `"Stage 6 Pending..."`
- **Unlocked Display**: `${consistencyIssues} Conflicts Mapped`

### 3. AI Assistant Card
- **Readiness Condition**: `doc.rag_ready || doc.rag_status === "completed" || doc.status === "completed"`
- **Status Indicator**: `"Interactive Q&A Ready"`
- **Locked Display**: `"Stage 5 Indexing..."`

### 4. Comparative Analysis Card
- **Readiness Condition**: `doc.comparative_analysis_ready || doc.comparative_analysis_status === "completed" || doc.status === "completed"`
- **Status Indicator**: `"Executive Benchmark Ready"`
- **Locked Display**: `"Stage 7 Pending..."`

---

## 4. Progress Percentage Calculation Formula

$$\text{Progress Percentage} = \frac{\text{Count of Completed or Skipped Stages}}{8} \times 100\%$$

| Completed Stages Count | Exact Calculated Progress | Rendered Value |
| :---: | :---: | :---: |
| 0 | 0.0% | 0% |
| 1 | 12.5% | 12.5% |
| 2 | 25.0% | 25% |
| 3 | 37.5% | 37.5% |
| 4 | 50.0% | 50% |
| 5 | 62.5% | 62.5% |
| 6 | 75.0% | 75% |
| 7 | 87.5% | 87.5% |
| 8 | 100.0% | 100% |

No arbitrary hardcoding or static fallback steps are permitted.
