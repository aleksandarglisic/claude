# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**SecureShip** — a shipment customer-support chat app where a locally-run LLM (Ollama) verifies user identity conversationally before granting access to shipment data. The chat *is* the product; there is no traditional login for end users.

Full specification: `project_overview.md`  
Week-by-week build plan: `development_roadmap.md`  
Code lives in: `secureship/`

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async/asyncpg), Postgres 16
- **Frontend:** React 18 (Vite), TypeScript, React Query (via Orval), CSS Modules
- **LLM:** Ollama on the host at `http://host.docker.internal:11434`; model `qwen3:8b` (fallback `llama3.2:3b`)
- **Auth (admin only):** Auth0, via the Auth0 Agent Skills package (Week 4)
- **Codegen:** Orval generates all frontend TypeScript types and React Query hooks from `/openapi.json` — nothing is hand-written

## Transport Decision

**HTTP has been chosen.** Orval generates fully-wired React Query hooks for every endpoint. No WebSocket path.

## Commands

```bash
# Start the full stack (run from secureship/)
docker-compose up

# Rebuild after code changes that aren't hot-reloaded
docker-compose up --build

# Regenerate frontend types and hooks (run from secureship/frontend/)
npm run generate

# Seed the database with mock data
docker-compose exec backend python scripts/seed_data.py

# Pull the LLM (host machine, once)
ollama pull qwen3:8b
```

## Ports

| Service  | Host port | Notes |
|----------|-----------|-------|
| Frontend | 3000      | Vite dev server |
| Backend  | 8000      | FastAPI + uvicorn with `--reload` |
| Postgres | **5433**  | Mapped to 5433 (not 5432) — local Postgres already occupies 5432 |
| Ollama   | 11434     | Host machine only, not in Docker |

## Project Structure

```
secureship/
├── docker-compose.yml
├── docs/diagrams/          # Section 6 Mermaid diagrams (regenerate in Week 5)
├── backend/
│   ├── main.py             # FastAPI app, lifespan creates all tables via create_all
│   ├── db/session.py       # Async engine, SessionLocal, Base, get_db dependency
│   ├── llm/ollama_client.py
│   ├── models/             # Customer, Shipment, Package, ChatSession, enums
│   ├── routes/chat.py      # POST /chat — calls Ollama, persists transcript
│   ├── tools/              # Tool implementations (Week 2+)
│   └── scripts/seed_data.py
└── frontend/
    ├── orval.config.ts     # Points at localhost:8000/openapi.json
    └── src/
        ├── api/generated/  # Orval output — DO NOT hand-edit
        ├── components/ChatWindow/
        └── lib/axiosInstance.ts  # Orval mutator function
```

## Data Model

```
Customer     → id (str/uuid), first_name, last_name, phone_number (E.164), address
Shipment     → id, customer_id (FK), tracking_number, status (enum), carrier,
               origin, destination, estimated_delivery, last_update
Package      → id, shipment_id (FK), description, weight_kg, declared_value
ChatSession  → id, customer_id (nullable FK), state (enum), started_at,
               ended_at, transcript (JSONB)
```

`ChatSession.transcript` — array of `{role, content, timestamp, tool_calls?}` objects, one pair per exchange.  
`ChatSession.state` enum: `anonymous | collecting_identity | code_sent | awaiting_code | verified | escalated_to_human`  
`Shipment.status` enum: `label_created | in_transit | out_for_delivery | delivered | exception`

## Architecture Constraints

**Identity gate is enforced in the backend tool layer, not in the model's prompt.** The model calls tools; the backend decides whether to execute them based on `session.state`. Never move the check into the system prompt.

**Tool layer always uses `session.customer_id`**, never a customer ID supplied by the model or user. `lookup_shipments` takes no `customer_id` parameter.

**Two identity systems that must never intersect:**
1. Conversational verification (`ChatSession.state`) — session-scoped, for end users only
2. Auth0 JWT — admin panel only

**Ollama stays on the host.** The backend reaches it via `http://host.docker.internal:11434`. Running Ollama in Docker loses Apple Metal GPU acceleration.

**Session history is loaded from the DB transcript**, not from client-supplied history. The DB is the source of truth for conversation context.

## Tool Definitions (Week 2+)

| Tool | Parameters | What backend does |
|---|---|---|
| `request_identity_info()` | — | Transition state → `collecting_identity` |
| `verify_identity(first_name, last_name, address, phone_number)` | strings | Match Customer table; on match → generate code, set `pending_customer_id`, state → `code_sent` |
| `send_verification_code(customer_id)` | string | Generate 6-digit code, log to console |
| `lookup_shipments()` | — | `SELECT … WHERE customer_id = session.customer_id` |

## Key Conventions

- **No hand-written TypeScript types or fetch calls.** Run `npm run generate` from `frontend/` after any backend schema change and commit the output.
- **Admin auth via Auth0 Agent Skills** — install before starting Epic E, not mid-way through.
- **Mock data only.** Seed script at `backend/scripts/seed_data.py` is re-runnable and wipes existing data first.
- **Human escalation (Epic G) is purely cosmetic.** No backend logic beyond setting `state = escalated_to_human`.
- **2FA modal appears on demand**, triggered by backend signalling `code_sent` state — not pre-rendered.
