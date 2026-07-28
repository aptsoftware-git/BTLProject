# AI Document Intelligence & Proofreading Platform

An enterprise-grade AI-powered Document Intelligence platform that combines document proofreading, semantic understanding, contextual consistency analysis, retrieval-augmented generation (RAG), and comparative business intelligence into a unified workflow.

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

Features include:

- Grammar correction
- Spelling correction
- Writing style improvements
- Protected term detection
- Semantic validation
- Duplicate correction removal
- Intelligent merge strategy

Proofreading engines:

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

Capabilities include:

- Semantic chunking
- ChromaDB vector indexing
- Hybrid BM25 + vector retrieval
- Context-aware document Q&A
- Citation-grounded responses

---

## Comparative Analysis

Automatically analyzes company documents and performs market benchmarking.

Workflow includes:

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

```
Upload Document
        │
        ▼
Layout-Aware Extraction (Docling)
        │
        ▼
Document Preprocessing
        │
        ▼
Paragraph & Sentence Segmentation
        │
        ▼
Protected Terms Detection
        │
        ▼
Grammar & Spell Checking
(LanguageTool + SymSpell + Local LLM)
        │
        ▼
Semantic Validation
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
        ├──────────────► AI Document Assistant (RAG)
        │
        ├──────────────► Contextual Consistency Analysis
        │
        └──────────────► Comparative Analysis
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

# Installation

## Clone the repository

```bash
git clone <repository-url>
cd BTLProject
```

---

## Create a virtual environment

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / macOS

```bash
source .venv/bin/activate
```

---

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Download the spaCy model

```bash
python -m spacy download en_core_web_sm
```

---

# Additional Requirements

## Java Runtime

LanguageTool requires Java.

Install:

- Java Runtime Environment (JRE 17 or newer)

---

## SymSpell Dictionary

Download the English frequency dictionary from the SymSpell repository.

Place it here:

```
models/
    frequency_dictionary_en_82_765.txt
```

---

## Ollama

Install Ollama and start the server.

Default configuration:

```
OLLAMA_HOST=http://192.168.19.21:11434

OLLAMA_MODEL=qwen2.5-coder:32b
```

---

## Claude API

Set your API key inside the project `.env` file.

```
CLAUDE_API_KEY=xxxxxxxxxxxxxxxx


```

---

## Tavily Search API

Used for Comparative Analysis.

```
TAVILY_API_KEY=xxxxxxxxxxxxxxxx
```

---

# Running the Application

## Backend

```bash
python -m uvicorn backend.app:app --reload
```

---

## Frontend

```bash
cd ai-proofreader-frontend

npm install

npm run dev
```

---

# Project Structure

```
BTLProject/

backend/
src/
tests/
models/
data/

    input/
    output/

ai-proofreader-frontend/

requirements.txt
README.md
```

---

# Output Directory

Each uploaded document creates a dedicated output directory.

```
data/output/

    <document_id>/

        01_raw/
        02_layout/
        03_preprocessed/
        04_proofreading/
        05_rag/
        06_context_analysis/
        07_claude_verification/
        08_reports/
        09_comparative_analysis/
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

```
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

# Major Reports Generated

The platform automatically generates:

### Proofreading Report

Grammar, spelling, and writing quality improvements.

---

### Executive Audit Report

Claude-verified ambiguity and consistency findings.

---

### Context Analysis Report

Cross-document reasoning and semantic consistency analysis.

---

### Comparative Analysis Report

Business benchmarking, SWOT analysis, gap analysis, and strategic recommendations.

---

# Testing

Run all tests:

```bash
pytest tests/
```

Run a specific suite:

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
- Retrieval-augmented generation
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
- Fixed configuration inconsistencies by replacing obsolete global constants with structured configuration models.
- Added document-level sentence offset indexing for accurate highlighting and traceability.
- Replaced invalid `.dict()` usage on dataclasses with proper serialization utilities.
- Refactored the pipeline to use the actual class-based APIs for extraction, layout analysis, filtering, preprocessing, paragraph building, and sentence segmentation.
- Unified logging through the centralized pipeline logger.
- Eliminated duplicated HTML generation logic by reusing shared HTML templates.
- Added missing report artifacts, including CSV summaries and richer metadata.
- Performed end-to-end validation of all pipeline stages using lightweight test doubles for external dependencies such as spaCy, LanguageTool, SymSpell, and Ollama to ensure reliable data flow independent of runtime services.

---

# License

This project was developed as part of an AI-powered Document Intelligence internship project for enterprise document analysis and business intelligence workflows.