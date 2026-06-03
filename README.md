# SCM·INTEL — AI-Powered Supply Chain Risk Intelligence System

A production-grade, full-stack AI system that converts natural-language supply chain queries into prioritized, evidence-backed mitigation recommendations using a multi-agent LangGraph pipeline, hybrid RAG retrieval, and real-time streaming visualization.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Environment Setup](#environment-setup)
5. [Quick Start (Docker)](#quick-start-docker)
6. [Manual Setup (Local Dev)](#manual-setup-local-dev)
7. [Data Ingestion](#data-ingestion)
8. [Running the Application](#running-the-application)
9. [Sample Queries](#sample-queries)
10. [API Reference](#api-reference)
11. [Observability](#observability)
12. [Evaluation](#evaluation)
13. [Project Structure](#project-structure)

---

## Overview

**What it does:**

- Accepts natural-language queries about supply chain risks ("What are the critical delays affecting our electronics suppliers?")
- Runs a 6-node LangGraph agent pipeline: **Hybrid Retrieval → Supplier Risk → Shipment Analysis → Inventory Intelligence → Recommendation → LLM Judge**
- Streams real-time agent status updates to the frontend via Server-Sent Events (SSE)
- Returns prioritized P1/P2/P3 mitigation recommendations with rationale, timeline, and responsible team
- Tracks every decision in LangSmith for full observability
- Scores recommendation quality with DeepEval RAG metrics + LLM-as-judge

**Key capabilities:**

| Capability | Implementation |
|---|---|
| Hybrid retrieval | BM25 keyword + ChromaDB semantic → RRF fusion → CrossEncoder rerank |
| Agent orchestration | LangGraph StateGraph with typed shared state |
| Full observability | LangSmith tracing on every node with `@traceable` |
| Quality evaluation | DeepEval (AnswerRelevancy, Faithfulness, ContextualRecall) + GPT-4o judge |
| Real-time streaming | SSE from FastAPI → React EventSource → live agent flow visualization |
| Token optimization | tiktoken counting + context compression at 80% model limit |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION                           │
│  CSV → Chunker → OpenAI Embedder → ChromaDB + MySQL + BM25 pkl  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    QUERY PIPELINE (LangGraph)                    │
│                                                                  │
│  User Query                                                      │
│      │                                                           │
│      ▼                                                           │
│  [Hybrid Retrieval]  BM25 + ChromaDB → RRF → CrossEncoder       │
│      │                                                           │
│      ├──► [Supplier Risk Agent]    ──┐                           │
│      ├──► [Shipment Analysis Agent] ─┼──► [Recommendation Agent] │
│      └──► [Inventory Intel Agent]  ──┘         │                 │
│                                           [Evaluator]            │
│                                                │                 │
│                                          SSE Stream              │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      REACT FRONTEND                              │
│  Login → Dashboard → Query Console (live agent flow) →           │
│  Incidents → Suppliers → Observability → Architecture            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 | Exact version required for some ML dependencies |
| Node.js | 18+ | For frontend build |
| MySQL | 8.0+ | Local or via Docker |
| Docker + Compose | 24+ | Optional — for containerized setup |
| OpenAI API Key | — | `gpt-4o` + `text-embedding-3-small` |
| LangSmith Account | — | Free tier at [smith.langchain.com](https://smith.langchain.com) |

**Estimated API costs per query:** ~$0.05–0.15 USD (6 GPT-4o calls + embeddings)

---

## Environment Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd AI-Powered-SCM-Assistant

# 2. Copy the example env file
cp backend/.env.example backend/.env

# 3. Fill in required values in backend/.env
```

**Required values in `backend/.env`:**

```env
OPENAI_API_KEY=sk-...                          # From platform.openai.com
LANGCHAIN_API_KEY=ls__...                      # From smith.langchain.com
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=supply-chain-risk-intel
MYSQL_URL=mysql+aiomysql://root:root@localhost:3306/supply_chain_db
MYSQL_URL_SYNC=mysql+pymysql://root:root@localhost:3306/supply_chain_db
JWT_SECRET_KEY=<generate-with: openssl rand -hex 32>
```

---

## Quick Start (Docker)

```bash
# Start all services (MySQL + Backend + Frontend)
docker-compose up --build

# In a separate terminal, run database migrations
docker exec scm_backend alembic upgrade head

# Seed sample data (creates admin user + 6 seed incidents)
docker exec scm_backend python scripts/seed_db.py

# Generate and ingest sample supply chain data
docker exec scm_backend python data/generate_sample_data.py
docker exec scm_backend python scripts/ingest_data.py --csv data/supply_chain_data.csv
```

**Access:**
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/api/docs
- Default login: `admin@scm-intel.local` / `Admin@123`

---

## Manual Setup (Local Dev)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Create the MySQL database
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS supply_chain_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# Run Alembic migrations
alembic upgrade head

# Seed initial data
python scripts/seed_db.py

# Start the API server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Data Ingestion

### Option A: Use the included sample data generator

```bash
cd backend

# Generate 500 rows of realistic supply chain data
python data/generate_sample_data.py --rows 500

# Ingest into ChromaDB + MySQL + BM25 index
python scripts/ingest_data.py --csv data/supply_chain_data.csv
```

### Option B: Bring your own CSV

The CSV must contain these columns (any additional columns are ignored):

| Column | Type | Example |
|---|---|---|
| `IncidentCode` | string | `INC-00001` |
| `SupplierID` | string | `SUP-001` |
| `SupplierName` | string | `GlobalTech Components` |
| `Region` | string | `Asia-Pacific` |
| `SupplierCategory` | string | `Electronics` |
| `ReliabilityScore` | float (0–100) | `72.5` |
| `WarehouseLocation` | string | `Shanghai, China` |
| `ShipmentStatus` | string | `Delayed` |
| `DeliveryDelayDays` | float | `18.0` |
| `TransportationCost` | float | `45000.00` |
| `InventoryLevel` | float | `120.0` |
| `DemandForecast` | float | `800.0` |
| `IncidentCategory` | string | `supplier\|shipment\|inventory\|demand` |
| `Title` | string | `Critical port congestion` |
| `Description` | string | `Full incident description...` |
| `OccurredAt` | date (YYYY-MM-DD) | `2024-06-01` |
| `ResolutionStatus` | string | `open\|in_progress\|resolved\|closed` |

```bash
python scripts/ingest_data.py --csv path/to/your/data.csv

# Re-ingest (clears ChromaDB first)
python scripts/ingest_data.py --csv path/to/your/data.csv --reset-chroma
```

**What ingestion does:**
1. Loads CSV with pandas
2. Calculates severity from delay days + inventory/demand coverage ratio
3. Creates **record chunks** (one per row) and **supplier summary chunks** (one per supplier)
4. Generates OpenAI embeddings in batches of 100
5. Upserts all chunks into ChromaDB with metadata
6. Builds BM25 index → saves to `data/bm25_index.pkl`
7. Upserts suppliers and inserts incidents into MySQL

---

## Running the Application

### Backend API

```bash
# Development (hot-reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --workers 4 --port 8000
```

### Frontend

```bash
npm run dev       # Development (Vite HMR)
npm run build     # Production build
npm run preview   # Preview production build
```

### Tests

```bash
cd backend
pytest -v                          # All tests
pytest tests/test_agents.py -v     # Agent unit tests only
pytest tests/test_retrieval.py -v  # Retrieval tests
pytest tests/test_api.py -v        # API + evaluation tests
```

---

## Sample Queries

### Query 1: Supplier delay analysis

**Input:**
```
What supplier delays are affecting critical electronics components in Asia-Pacific?
```

**Expected agent outputs:**
- **Supplier Risk:** risk_level=critical, affected_suppliers=[SUP-001, SUP-002], trend=degrading
- **Shipment Analysis:** delay_probability=0.84, estimated_delay_days=16.2, hotspot=Shanghai
- **Inventory Intel:** stockout_risk_items=[PCB, Capacitors], days_until_stockout=3
- **Recommendation:** P1 – Emergency reorder from alternative supplier within 24h

---

### Query 2: Inventory stockout risk

**Input:**
```
Which products are at risk of stockout and what are the reorder recommendations?
```

**Expected:** List of items below safety stock with urgency-tiered reorder actions (immediate/soon/planned)

---

### Query 3: Transportation cost spike

**Input:**
```
Transportation cost spike detected on North America routes — what should we do?
```

**Expected:** Cost impact analysis, alternative routing options, carrier diversification recommendations

---

## API Reference

### Authentication

```bash
# Register a new user
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@company.com","password":"SecurePass123","full_name":"Jane Smith"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@scm-intel.local","password":"Admin@123"}'
# → Returns {"data": {"access_token": "eyJ...", "refresh_token": "eyJ..."}}

export TOKEN="eyJ..."
```

### Query (streaming SSE)

```bash
# Stream a supply chain query
curl -X POST http://localhost:8000/api/query/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query":"What are the critical supplier risks for electronics components?"}' \
  --no-buffer

# Events stream:
# data: {"type":"agent_started","agent":"retrieval",...}
# data: {"type":"agent_completed","agent":"retrieval",...}
# data: {"type":"agent_started","agent":"supplier_risk",...}
# ...
# data: {"type":"final_result","data":{"recommendations":[...],"risk_score":87},...}
```

### Query (synchronous)

```bash
curl -X POST http://localhost:8000/api/query/sync \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"Port congestion impacting our shipment schedules","filters":{"severity":"critical"}}'
```

### Incidents

```bash
# List incidents (with filters)
curl "http://localhost:8000/api/incidents?severity=critical&limit=20" \
  -H "Authorization: Bearer $TOKEN"

# Get single incident
curl http://localhost:8000/api/incidents/INC-00001 \
  -H "Authorization: Bearer $TOKEN"
```

### Suppliers

```bash
# List all suppliers sorted by reliability
curl http://localhost:8000/api/suppliers \
  -H "Authorization: Bearer $TOKEN"

# Get supplier detail with recent incidents
curl http://localhost:8000/api/suppliers/SUP-001 \
  -H "Authorization: Bearer $TOKEN"

# Performance history (for charts)
curl "http://localhost:8000/api/suppliers/SUP-001/history?limit=30" \
  -H "Authorization: Bearer $TOKEN"
```

### Dashboard

```bash
# KPIs
curl http://localhost:8000/api/dashboard/kpis \
  -H "Authorization: Bearer $TOKEN"

# Live alert feed
curl "http://localhost:8000/api/dashboard/alerts?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

### Evaluation

```bash
# Trigger DeepEval evaluation for a session
curl -X POST http://localhost:8000/api/evaluation/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<session-id>"}'

# View evaluation results
curl http://localhost:8000/api/evaluation/results \
  -H "Authorization: Bearer $TOKEN"
```

---

## Observability

### LangSmith Dashboard

Every agent call is automatically traced when `LANGCHAIN_TRACING_V2=true` and a valid `LANGCHAIN_API_KEY` is set.

**What's traced:**
- Full input/output for each agent node
- Token usage per call (prompt + completion)
- Latency per agent and end-to-end
- Error details with full stack traces
- Retrieved documents and similarity scores

**Access your traces:**
→ https://smith.langchain.com → Select project `supply-chain-risk-intel`

### In-app Observability Page

The **Observatory** page (`/observability`) shows:
- Average response time per agent (bar chart)
- Query volume over 7 days (line chart)
- LangSmith run explorer (recent traces table)
- Estimated API cost today

### Pulling metrics via API

```bash
# Aggregated metrics from today
curl http://localhost:8000/api/observability/metrics \
  -H "Authorization: Bearer $TOKEN"

# Recent LangSmith runs
curl "http://localhost:8000/api/observability/runs?limit=20" \
  -H "Authorization: Bearer $TOKEN"

# Full trace detail
curl http://localhost:8000/api/observability/trace/<run-id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Evaluation

### Run the full evaluation suite

```bash
cd backend

# Evaluate last 20 query sessions
python scripts/evaluate.py

# Evaluate last 50 sessions and export results
python scripts/evaluate.py --limit 50 --export evaluation_results.json

# Evaluate a specific session
python scripts/evaluate.py --session-id <session-id>
```

**Metrics computed:**

| Metric | Tool | Threshold | Meaning |
|---|---|---|---|
| Answer Relevancy | DeepEval | ≥ 0.70 | Is the answer relevant to the query? |
| Faithfulness | DeepEval | ≥ 0.80 | Does the answer stay grounded in retrieved context? |
| Contextual Recall | DeepEval | ≥ 0.70 | Does the context cover the information needed? |
| Judge Feasibility | GPT-4o | 0–10 | Can the recommendation actually be implemented? |
| Judge Specificity | GPT-4o | 0–10 | Names specific suppliers/routes/SKUs? |
| Judge Impact | GPT-4o | 0–10 | Meaningfully reduces risk? |
| Judge Timeline | GPT-4o | 0–10 | Is the timeframe realistic? |

**Verdict thresholds:**
- **APPROVED** — overall judge score ≥ 7.5
- **NEEDS_REVISION** — overall score ≥ 5.0
- **REJECTED** — overall score < 5.0

---

## Project Structure

```
AI-Powered-SCM-Assistant/
├── backend/
│   ├── app/
│   │   ├── agents/          # LangGraph nodes + state + graph builder
│   │   ├── api/routes/      # FastAPI routers (auth, query, incidents…)
│   │   ├── database/        # SQLAlchemy models + async connection
│   │   ├── evaluation/      # DeepEval metrics + LLM judge
│   │   ├── ingestion/       # Chunker + OpenAI embedder + pipeline
│   │   ├── retrieval/       # ChromaDB + BM25 + CrossEncoder + hybrid
│   │   ├── schemas/         # Pydantic v2 request/response models
│   │   └── utils/           # Token optimizer + guardrails
│   ├── alembic/             # Database migration scripts
│   ├── data/                # CSV data + BM25 pickle artefacts
│   ├── scripts/             # ingest_data.py, seed_db.py, evaluate.py
│   ├── tests/               # pytest unit + integration tests
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios client + TanStack Query + SSE stream
│   │   ├── components/      # layout/, ui/, agent-flow/, dashboard/
│   │   ├── pages/           # Dashboard, QueryConsole, Incidents…
│   │   ├── store/           # Zustand global store
│   │   └── types/           # TypeScript interfaces
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── README.md
```

---

## Tech Stack

**Backend:** Python 3.11 · FastAPI · LangGraph · LangChain · LangSmith · OpenAI GPT-4o · ChromaDB · MySQL · BM25 · CrossEncoder · DeepEval · SQLAlchemy · Alembic · Pydantic v2

**Frontend:** React 18 · TypeScript · Vite · Tailwind CSS v3 · Zustand · TanStack Query · Recharts · React Flow · Framer Motion · Axios

**Infrastructure:** Docker · MySQL 8 · Nginx · uvicorn
