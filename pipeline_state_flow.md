# Pipeline State Flow & Transition Architecture

## Overview
This document specifies the lifecycle state transitions, automatic polling mechanism, stage unlocking rules, and error recovery flows governing document processing in the platform.

---

## 1. Lifecycle State Machine Diagram

```mermaid
stateDiagram-v2
    [*] --> Uploaded: POST /documents/upload
    Uploaded --> Processing: Background Worker Started
    
    state Processing {
        [*] --> Stage1_Completed: Stage 1: Document Uploaded
        Stage1_Completed --> Stage2_Running: Start Stage 2
        Stage2_Running --> Stage2_Completed: Document Content Extraction
        Stage2_Completed --> Stage3_Running: Start Stage 3
        Stage3_Running --> Stage3_Completed: Language & Spelling Review
        Stage3_Completed --> Stage4_Running: Start Stage 4
        Stage4_Running --> Stage4_Completed: Grammar & Writing Quality Review
        Stage4_Completed --> Stage5_Running: Start Stage 5
        Stage5_Running --> Stage5_Completed: Knowledge Index Creation
        Stage5_Completed --> Stage6_Running: Start Stage 6
        Stage6_Running --> Stage6_Completed: Consistency & Contradiction Review
        Stage6_Completed --> Stage7_Running: Start Stage 7
        Stage7_Running --> Stage7_Completed: Competitive Benchmark Analysis
        Stage7_Completed --> Stage8_Running: Start Stage 8
        Stage8_Running --> Stage8_Completed: Executive Insights Report
    }

    Processing --> Failed: Stage Execution Exception
    Failed --> Processing: POST /jobs/{id}/retry
    Stage8_Completed --> Completed: All 8 Stages Finalized (100%)
    Completed --> [*]
```

---

## 2. Dynamic Frontend Polling Flow

```mermaid
sequenceDiagram
    autonumber
    participant UI as Workspace Frontend
    participant API as FastAPI Backend
    participant Worker as Background Orchestrator Worker

    UI->>API: GET /documents/{job_id}
    API-->>UI: Return job status, stages array, readiness flags
    
    alt Incomplete Pipeline (Status: processing/pending OR Running/Pending stages present)
        UI->>UI: Update state: badges, progress %, executive cards
        UI->>UI: Set timer (setTimeout 1500ms)
        UI->>API: GET /documents/{job_id}
        API-->>UI: Return updated stage state (e.g. Stage 5 Completed)
        UI->>UI: Instantly unlock AI Assistant tab & recalculate progress %
    else All 8 Stages Completed (Status: completed, Progress: 100%)
        UI->>UI: Clear timer & stop polling
        UI->>UI: Render fully unlocked workspace
    end
```

---

## 3. Feature Unlock Dependency Rules

```mermaid
flowchart TD
    S1[Stage 1: Document Uploaded] -->|Unlocks| F1[Upload Metadata]
    S2[Stage 2: Document Content Extraction] -->|Unlocks| F2[Document Viewer & Raw Text]
    S3[Stage 3: Language & Spelling Review] -->|Unlocks| F3[Spelling Candidates]
    S4[Stage 4: Grammar & Writing Quality Review] -->|Unlocks| F4[Proofreading Tab & Clean Preview]
    S5[Stage 5: Knowledge Index Creation] -->|Unlocks| F5[AI Assistant Tab - Interactive Q&A]
    S6[Stage 6: Consistency & Contradiction Review] -->|Unlocks| F6[Ambiguity Analysis Tab - Conflict Mapping]
    S7[Stage 7: Competitive Benchmark Analysis] -->|Unlocks| F7[Comparative Analysis Tab - Peer Benchmarks]
    S8[Stage 8: Executive Insights Report] -->|Unlocks| F8[Reports Tab - Multi-Format Exports]
```

---

## 4. Stage Failure & Auto-Resume Flow

1. **Failure Signal**: If an uncaught exception occurs during stage execution (e.g., in Stage 5: Knowledge Index Creation), the orchestrator catches the exception, updates stage status to `Failed`, and sets `s.errors = traceback.format_exc()`.
2. **UI Notification**: Polling detects `status === "Failed"` for Stage 5. `StagePipelineCard` turns Stage 5 red, displays the exact failure reason snippet, and renders a "Retry Stage" button.
3. **User Action**: The user clicks "Retry Stage" on Stage 5.
4. **Backend Reset**: Frontend calls `POST /jobs/{job_id}/retry?stage_id=stage_5_rag`. Backend sets Stage 5 status to `Pending`, clears errors, sets job status to `pending`, saves metadata, and enqueues job in background worker.
5. **Resume Polling**: Frontend immediately updates UI state and restarts 1.5s polling loop. Stage 5 status updates `Pending` $\rightarrow$ `Running` $\rightarrow$ `Completed`.
