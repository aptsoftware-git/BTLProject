# AI Document Intelligence & Proofreading Platform

An enterprise-grade AI-powered Document Intelligence platform that combines document proofreading, semantic understanding, contextual consistency analysis, Retrieval-Augmented Generation (RAG), and comparative business intelligence into a unified workflow.

The platform is designed to analyze business documents such as company brochures, annual reports, policy documents, handbooks, and technical documentation while generating executive-quality reports and actionable business insights.

---

# Key Features

## Intelligent Document Processing

- PDF, DOCX, and TXT document support
- Layout-aware extraction using **Docling**
- Preservation of document structure, headings, tables, images, and reading order
- Automatic paragraph and sentence segmentation
- OCR-ready architecture

---

## AI-Powered Proofreading

A multi-stage proofreading engine combining deterministic NLP techniques with Large Language Models.

### Features

- Grammar correction
- Spelling correction
- Writing style improvements
- Protected term detection
- Semantic validation
- Duplicate correction removal
- Intelligent merge strategy

### Proofreading Engines

- LanguageTool
- SymSpell
- Local LLM (Ollama)
- Semantic Validation Layer

---

## Contextual Consistency Analysis

Beyond proofreading, the platform performs document-level reasoning to identify:

- Ambiguous statements
- Missing information
- Contradictions
- Cross-section inconsistencies
- Broken references
- Numeric inconsistencies
- Policy conflicts
- Terminology inconsistencies

Each finding is validated through Claude before appearing in the final executive report.

---

## Retrieval-Augmented Generation (RAG)

The platform builds a semantic knowledge base for every uploaded document.

### Capabilities

- Semantic chunking
- ChromaDB vector indexing
- Hybrid BM25 + Vector Retrieval
- Context-aware document Q&A
- Citation-grounded responses

---

## Comparative Analysis

Automatically analyzes company documents and performs market benchmarking.

### Workflow

- Company understanding
- Industry identification
- Competitor discovery
- Competitor profiling
- Comparative benchmarking
- Gap analysis
- SWOT analysis
- Strategic recommendations

Outputs a single executive-grade comparative analysis report.

---

# Architecture Overview

```text
                           Upload Document
                                  │
                                  ▼
                 Layout-Aware Extraction (Docling)
                                  │
                                  ▼
                    Document Preprocessing Pipeline
                                  │
                                  ▼
              Paragraph & Sentence Segmentation
                                  │
                                  ▼
                 Protected Terms Identification
                                  │
                                  ▼
           Grammar & Spell Checking Pipeline
      (LanguageTool + SymSpell + Local LLM)
                                  │
                                  ▼
                    Semantic Validation Layer
                                  │
                                  ▼
                 Proofreading Report Generation
                                  │
                                  ▼
                      Semantic Chunking
                                  │
                                  ▼
                    Embedding Generation
                                  │
                                  ▼
                      ChromaDB Vector Store
                                  │
          ┌───────────────────────┼────────────────────────┐
          │                       │                        │
          ▼                       ▼                        ▼
 AI Document Assistant    Context Analysis     Comparative Analysis
         (RAG)
```

---

# Technology Stack

## Backend

- Python
- FastAPI
- Docling
- spaCy
- LanguageTool
- SymSpell
- Ollama
- Anthropic Claude API
- ChromaDB
- SentenceTransformers

---

## Frontend

- React
- Vite
- Tailwind CSS
- JavaScript

---

## AI Models

### Local Models

- Ollama
- Qwen
- Local Grammar Correction Model

### Cloud Models

- Claude (Business Understanding & Verification)

---

# Prerequisites

Before running the project, ensure the following software is installed:

- Python 3.11 or newer
- Node.js (v18 or newer recommended)
- npm
- Git
- Java Runtime Environment (JRE 17 or newer)
- Ollama (for local LLM inference)

---

# Getting Started

## 1. Clone the Repository

```bash
git clone <repository-url>
cd BTLProject
```

---

## 2. Create a Virtual Environment

### Windows

```bash
python -m venv .venv

.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv

source .venv/bin/activate
```

---

## 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Install Frontend Dependencies

```bash
cd ai-proofreader-frontend

npm install

cd ..
```

---

## 5. Download the spaCy Language Model

```bash
python -m spacy download en_core_web_sm
```

---

# Environment Configuration

Create a `.env` file in the project root.

You can either create it manually or copy an existing template:

```bash
cp .env.example .env
```

Example configuration:

```env
# Claude API
CLAUDE_API_KEY=your_claude_api_key

# Tavily Search API
TAVILY_API_KEY=your_tavily_api_key

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:32b
```

### Environment Variables

| Variable | Description |
|-----------|-------------|
| `CLAUDE_API_KEY` | API key used for Claude-powered business understanding and verification |
| `TAVILY_API_KEY` | API key used for web search during Comparative Analysis |
| `OLLAMA_HOST` | URL of your local or remote Ollama server |
| `OLLAMA_MODEL` | Name of the Ollama model to use |

> **Note:** Never commit your `.env` file to version control.

---

# Additional Requirements

## Java Runtime

LanguageTool requires Java Runtime Environment (JRE 17 or newer).

Verify installation:

```bash
java -version
```

---

## SymSpell Dictionary

Download the English frequency dictionary from the official SymSpell repository.

Place the file at:

```text
models/
└── frequency_dictionary_en_82_765.txt
```

---

## Ollama Setup

Install Ollama by following the official installation instructions for your operating system.

Pull the model you intend to use:

```bash
ollama pull <model-name>
```

Start the Ollama server:

```bash
ollama serve
```

Ensure that the model specified in your `.env` file is available.

---

# Running the Application

## Start the Backend

```bash
python -m uvicorn backend.app:app --reload
```

---

## Start the Frontend

Open a new terminal:

```bash
cd ai-proofreader-frontend

npm run dev
```

---

# Verifying the Installation

Once both services are running:

1. Open the frontend in your browser.
2. Upload a sample document.
3. Verify that:
   - Proofreading completes successfully.
   - Reports are generated.
   - AI Document Assistant answers document-related questions.
   - Context Analysis generates an executive report.
   - Comparative Analysis completes successfully (if API keys are configured).

---

# Project Structure

```text
BTLProject/
│
├── backend/
├── src/
├── tests/
├── models/
├── data/
│   ├── input/
│   └── output/
│
├── ai-proofreader-frontend/
│
├── requirements.txt
├── README.md
└── .env
```

---

# Output Directory

Each uploaded document creates a dedicated output directory.

```text
data/output/

<document_id>/

├── 01_raw/
├── 02_layout/
├── 03_preprocessed/
├── 04_proofreading/
├── 05_rag/
├── 06_context_analysis/
├── 07_claude_verification/
├── 08_reports/
└── 09_comparative_analysis/
```

Generated artifacts include:

- Annotated HTML
- Corrected HTML
- JSON reports
- Markdown reports
- CSV summaries
- Executive audit reports
- Comparative analysis reports

---

# Comparative Analysis Workflow

```text
Company Brochure
        │
        ▼
Business Context Retrieval
        │
        ▼
Claude Business Understanding
        │
        ▼
Verified Company Profile
        │
        ▼
Dynamic Search Query Generation
        │
        ▼
Tavily Search
        │
        ▼
Competitor Verification
        │
        ▼
Claude Competitor Profiling
        │
        ▼
Comparative Analysis
        │
        ▼
Gap Analysis
        │
        ▼
SWOT Analysis
        │
        ▼
Strategic Recommendations
        │
        ▼
Executive Comparative Analysis Report
```

---

# Reports Generated

The platform automatically generates:

## Proofreading Report

Grammar, spelling, and writing quality improvements.

---

## Executive Audit Report

Claude-verified ambiguity and consistency findings.

---

## Context Analysis Report

Cross-document reasoning and semantic consistency analysis.

---

## Comparative Analysis Report

Business benchmarking, SWOT analysis, gap analysis, and strategic recommendations.

---

# Testing

Run the complete test suite:

```bash
pytest tests/
```

Run specific test suites:

```bash
python -m unittest tests/test_backend_integration.py
```

```bash
python -m unittest tests/test_comparative_analysis_workflow.py
```

---

# Design Principles

The platform follows several core engineering principles:

- Modular architecture
- Dependency injection
- Pipeline-based execution
- Retrieval-Augmented Generation (RAG)
- Explainable AI outputs
- Grounded LLM responses
- Enterprise-grade reporting
- Zero modification of original documents
- Production-ready backend APIs

---

# Recent Improvements

The project has been significantly refactored to improve maintainability, modularity, and end-to-end reliability.

Major improvements include:

- Introduced dependency injection across all pipeline components using a centralized configuration object.
- Replaced obsolete global constants with structured configuration models.
- Added document-level sentence offset indexing for accurate highlighting and traceability.
- Replaced invalid `.dict()` usage on dataclasses with proper serialization utilities.
- Refactored the pipeline to use class-based APIs for extraction, layout analysis, preprocessing, paragraph building, and sentence segmentation.
- Unified logging through a centralized pipeline logger.
- Eliminated duplicated HTML generation logic by reusing shared templates.
- Added richer report artifacts, including CSV summaries and metadata.
- Performed end-to-end validation using lightweight test doubles for external dependencies such as spaCy, LanguageTool, SymSpell, and Ollama, ensuring reliable execution independent of runtime services.

---

# Recommended Repository Files

## `.env.example`

```env
# Claude API
CLAUDE_API_KEY=

# Tavily Search API
TAVILY_API_KEY=

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=
```

---

## `.gitignore`

```gitignore
# Python
.venv/
__pycache__/
*.pyc

# Environment
.env

# Node
node_modules/

# Generated Outputs
data/output/

# IDE
.vscode/
.idea/
```

---

# License

This project was developed as part of an AI-powered Document Intelligence internship project focused on enterprise document analysis, proofreading, semantic reasoning, and business intelligence workflows.
