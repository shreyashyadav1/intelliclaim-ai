# IntelliClaim AI

**Insurance Document Intelligence Platform** — AI-powered claim processing, extraction, RAG search, and risk detection.

![Tech Stack](https://img.shields.io/badge/React-19-blue?logo=react) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi) ![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-black?logo=openai) ![MongoDB](https://img.shields.io/badge/MongoDB-7.0-green?logo=mongodb) ![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)

## Features

- **📄 Intelligent Document Processing** — Upload PDFs/images, OCR extraction, auto-classification
- **🤖 AI Data Extraction** — GPT-4o powered structured extraction of claim data
- **🔍 RAG Search** — Natural language queries across all claim documents
- **⚠️ AI Risk Detection** — Automated fraud detection, duplicate claims, suspicious billing
- **📊 Analytics Dashboard** — Claims trends, risk distribution, real-time stats

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 19, Vite 8, Recharts, Lucide Icons |
| **Backend** | Python FastAPI, Pydantic v2, Motor (async MongoDB) |
| **AI/ML** | OpenAI GPT-4o, LangChain, LlamaIndex, ChromaDB |
| **Database** | MongoDB Atlas / Local |
| **Storage** | AWS S3 / Local filesystem |
| **DevOps** | Docker, Docker Compose |

## Quick Start

### Prerequisites
- Node.js ≥ 20.19
- Python ≥ 3.11
- MongoDB (local or Atlas)
- OpenAI API Key (optional — app works with demo data)

### 1. Clone & Configure

```bash
cd intelliclaim-ai
cp .env.example backend/.env
# Edit backend/.env with your API keys
```

### 2. Backend Setup

```bash
cd backend
python3.11 -m venv venv
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

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/upload` | Upload & process document |
| `GET` | `/api/documents` | List documents |
| `GET` | `/api/claims` | List claims (with filters) |
| `GET` | `/api/claims/:id` | Claim detail |
| `POST` | `/api/extract/:doc_id` | AI extraction |
| `POST` | `/api/rag/query` | RAG search |
| `POST` | `/api/validate/:claim_id` | Risk validation |
| `GET` | `/api/analytics/overview` | Dashboard stats |

## Project Structure

```
intelliclaim-ai/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── main.py              # FastAPI app
│   ├── config.py             # Settings
│   ├── seed_data.py          # Demo data seeder
│   ├── models/               # Pydantic models
│   ├── routers/              # API endpoints
│   ├── services/             # Business logic
│   ├── db/                   # MongoDB connection
│   └── utils/                # Helpers
└── frontend/
    ├── src/
    │   ├── components/       # React components
    │   ├── pages/            # Route pages
    │   ├── services/         # API client
    │   └── hooks/            # Custom hooks
    └── index.html
```

## Skills Demonstrated

- OpenAI API & GPT-4o structured extraction
- LangChain & LlamaIndex RAG pipelines
- FastAPI async backend architecture
- React 19 with modern design patterns
- MongoDB aggregation pipelines
- Docker containerization
- Premium UI/UX design

## License

MIT
