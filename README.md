# IntelliClaim AI

**Insurance Document Intelligence Platform** — AI-powered claim processing, extraction, RAG search, and risk detection.

![React](https://img.shields.io/badge/React-19.2.7-blue?logo=react) ![FastAPI](https://img.shields.io/badge/FastAPI-0.137.2-green?logo=fastapi) ![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-black?logo=openai) ![MongoDB](https://img.shields.io/badge/MongoDB-7.0-green?logo=mongodb) ![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker) ![LangChain](https://img.shields.io/badge/LangChain-1.3.10-orange) ![LlamaIndex](https://img.shields.io/badge/LlamaIndex-0.14.22-purple)

---

## Overview

IntelliClaim AI is an end-to-end AI-powered insurance document intelligence platform that automates claim ingestion, document processing, and structured data extraction from medical reports, invoices, and insurance forms.

### What I Built

- **Developed an end-to-end AI-powered insurance document intelligence platform** using React, FastAPI, OpenAI GPT-4o, MongoDB, and Docker, automating document ingestion, OCR processing, and structured claim data extraction from medical reports, invoices, and insurance forms.

- **Engineered a Retrieval-Augmented Generation (RAG) system** using LangChain, LlamaIndex, ChromaDB, and OpenAI Embeddings, enabling semantic search and natural-language querying across insurance claim documents and historical records.

- **Built AI-assisted validation and risk-analysis workflows** leveraging GPT-4o function calling, OCR pipelines, and hybrid scoring models to identify missing information, duplicate submissions, suspicious billing patterns, and potential fraud indicators.

- **Architected scalable backend services** using asynchronous FastAPI APIs, modular service-oriented design, MongoDB aggregation analytics, and containerized deployment, supporting document indexing, claim processing, and operational reporting.

---

## Features

- **📄 Intelligent Document Processing** — Upload PDFs/images, OCR extraction via PyMuPDF + pytesseract, AI-powered document classification (GPT-4o with keyword fallback)
- **🤖 AI Data Extraction** — GPT-4o with function calling for structured claim field extraction; realistic demo data fallback when no API key is configured
- **🔍 RAG Search** — LlamaIndex (VectorStoreIndex + ChromaVectorStore) for document indexing with OpenAI Embeddings; LangChain LCEL retrieval chain (Chroma retriever + ChatOpenAI + StrOutputParser) for natural-language Q&A
- **⚠️ AI-Assisted Risk Detection** — Hybrid scoring model: rule-based checks (missing fields, duplicates, billing thresholds, date logic) + GPT-4o function calling for billing anomalies, diagnosis inconsistencies, and suspicious patterns
- **📊 Analytics Dashboard** — MongoDB aggregation pipelines for claims trends, risk distribution, and real-time operational stats

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 19.2.7, Vite 8.0.16, React Router 7.18.0, Recharts, Lucide Icons |
| **Backend** | Python 3.13, FastAPI 0.137.2, Pydantic v2, Motor 3.7.1 (async MongoDB) |
| **AI/ML** | OpenAI GPT-4o, LangChain 1.3.10, LlamaIndex 0.14.22, ChromaDB 1.5.9, OpenAI Embeddings (text-embedding-3-small) |
| **Database** | MongoDB 7.0 (Atlas or Local) |
| **Storage** | AWS S3 / Local filesystem |
| **DevOps** | Docker, Docker Compose |

---

## Quick Start

### Prerequisites
- Node.js ≥ 20.19
- Python ≥ 3.11
- MongoDB (local or Atlas)
- OpenAI API Key (optional — app works with demo data)

### 1. Clone & Configure

```bash
git clone https://github.com/shreyashyadav1/intelliclaim-ai.git
cd intelliclaim-ai
cp .env.example backend/.env
# Edit backend/.env with your API keys
```

### 2. Backend Setup

```bash
cd backend
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Seed demo data
python seed_data.py

# Start the API
uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Docker (Alternative)

```bash
docker-compose up -d
```

Open **http://localhost:5173** (or the port shown by Vite).

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload` | Upload & process document (OCR + classification) |
| `GET`  | `/api/documents` | List documents |
| `GET`  | `/api/claims` | List claims (with filters) |
| `GET`  | `/api/claims/:id` | Claim detail |
| `POST` | `/api/extract/:doc_id` | AI extraction (GPT-4o function calling) |
| `POST` | `/api/rag/query` | RAG search (LangChain + ChromaDB + OpenAI Embeddings) |
| `POST` | `/api/validate/:claim_id` | Risk validation (rule-based + AI-assisted) |
| `POST` | `/api/batch-validate` | Batch validation |
| `GET`  | `/api/analytics/overview` | Dashboard stats |

---

## Implementation Details

This section maps each resume claim to the exact code implementation.

### RAG System: LangChain + LlamaIndex + ChromaDB + OpenAI Embeddings

| Component | Implementation | File |
|-----------|---------------|------|
| **LlamaIndex Document Indexing** | `VectorStoreIndex` + `ChromaVectorStore` + `OpenAIEmbedding` (text-embedding-3-small) | `services/rag_service.py` — `index_document()` |
| **LangChain Retrieval Chain** | `Chroma` retriever (OpenAIEmbeddings) → `ChatPromptTemplate` → `ChatOpenAI` (GPT-4o) → `StrOutputParser` | `services/rag_service.py` — `_query_with_langchain()` |
| **OpenAI Embeddings** | Explicit `OpenAIEmbeddings(model="text-embedding-3-small")` passed to both LlamaIndex and LangChain Chroma retriever | `services/rag_service.py` |

### AI-Assisted Validation & Risk Analysis

| Component | Implementation | File |
|-----------|---------------|------|
| **Rule-based checks** | Missing fields, duplicate detection (MongoDB), billing thresholds, date logic | `services/validation_service.py` — `_check_*()` methods |
| **AI-assisted review** | GPT-4o function calling with `assess_claim_risk` tool schema | `services/validation_service.py` — `_ai_validate_claim()` |
| **Hybrid scoring** | `rule_score + (ai_score × 0.4 × confidence)` | `services/validation_service.py` — `_calculate_risk_score()` |

### Document Processing & Extraction

| Component | Implementation | File |
|-----------|---------------|------|
| **OCR** | PyMuPDF for PDFs, pytesseract for images | `services/ocr_service.py` — `extract_text()` |
| **Document Classification** | GPT-4o classifier with keyword-based fallback | `services/ocr_service.py` — `classify_document()` |
| **Structured Extraction** | GPT-4o with function calling (`extract_claim_fields` tool) | `services/extraction_service.py` — `_extract_with_openai()` |

### Backend Architecture

| Component | Implementation | File |
|-----------|---------------|------|
| **Async FastAPI** | Lifespan hooks, async Motor, async routers | `main.py`, `db/connection.py` |
| **Modular services** | OCR, Extraction, RAG, Validation, Analytics, Storage | `services/*.py` |
| **MongoDB Analytics** | Aggregation pipelines for trends, risk distribution, overview | `services/analytics_service.py` |
| **Containerization** | Docker + Docker Compose (3 services) | `docker-compose.yml`, `Dockerfile` |

---

## Project Structure

```
intelliclaim-ai/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── main.py                 # FastAPI app (lifespan, CORS, routers)
│   ├── config.py               # Settings (Pydantic v2)
│   ├── seed_data.py            # Demo data seeder
│   ├── models/                 # Pydantic models
│   ├── routers/                # API endpoints (documents, claims, extraction, rag, analytics, validation)
│   ├── services/               # Business logic
│   │   ├── ocr_service.py      # OCR + document classification
│   │   ├── extraction_service.py # GPT-4o structured extraction
│   │   ├── rag_service.py        # LlamaIndex + LangChain RAG
│   │   ├── validation_service.py # Rule-based + AI-assisted validation
│   │   ├── analytics_service.py  # MongoDB aggregation pipelines
│   │   └── storage_service.py    # File storage (local/S3)
│   ├── db/                     # MongoDB connection (Motor)
│   └── utils/                  # PDF parser, helpers
└── frontend/
    ├── src/
    │   ├── components/         # React components (Layout, etc.)
    │   ├── pages/              # Route pages (Dashboard, Documents, Claims, RAG, Validation)
    │   ├── services/           # API client (axios)
    │   └── hooks/              # Custom hooks
    └── index.html
```

---

## Skills Demonstrated

- OpenAI API & GPT-4o structured extraction with function calling
- LangChain LCEL retrieval chains (Chroma + OpenAI Embeddings + ChatOpenAI)
- LlamaIndex vector indexing (VectorStoreIndex + ChromaVectorStore + OpenAIEmbedding)
- FastAPI async backend architecture with Motor (async MongoDB)
- React 19 with modern design patterns (Vite, React Router 7)
- MongoDB aggregation pipelines for analytics
- Docker containerization with multi-service Compose
- AI-assisted validation workflows (GPT-4o function calling + hybrid scoring)
- Premium UI/UX design

## License

MIT
