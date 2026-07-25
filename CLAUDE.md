# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**SecureShip** — a shipment customer-support chat app where a locally-run LLM (Ollama) verifies user identity conversationally before granting access to shipment data. The chat *is* the product; there is no traditional login for end users.

Full specification: `project_overview.md`  
Week-by-week build plan: `development_roadmap.md`

## Stack

- **Backend:** Python, FastAPI, SQLAlchemy, Postgres 16
- **Frontend:** React (Vite), TypeScript, React Query (via Orval), Zustand (WebSocket path only)
- **LLM:** Ollama running on the host machine at `http://host.docker.internal:11434`; primary model `qwen3:8b`, fallback `llama3.2:3b`
- **Auth (admin only):** Auth0, integrated via the Auth0 Agent Skills package
- **Codegen:** Orval generates all frontend TypeScript types and React Query hooks from the backend's `/openapi.json` — nothing is hand-written

## Transport Decision

Before writing any chat plumbing, the team must pick one and stick to it:
- **HTTP (Section 6.3):** simpler; Orval generates fully-wired hooks for every endpoint
- **WebSocket (Section 6.3b):** better real-time UX; WS message envelope types require dummy FastAPI endpoints so they appear in the OpenAPI schema for Orval to export (see `backend/routes/_types_chat_events.py`)

## Architecture Constraints

**Identity gate is enforced in the backend tool layer, not in the model's prompt.** The model calls tools; the backend decides whether to execute them based on `session.state`. This is the project's core teaching point — never move the check into the system prompt.

**Tool layer always uses `session.customer_id`**, never a customer ID supplied by the model or the user. The `lookup_shipments` tool takes no `customer_id` parameter for this reason.

**Two identity systems that must never intersect:**
1. Conversational verification (`ChatSession.state`) — for end users, session-scoped only
2. Auth0 JWT — for admin panel only

No code path should let an admin become a verified chat session, or let a chat session reach `/admin/*` routes.

**Ollama stays on the host** (not in Docker) to preserve Apple Metal GPU acceleration. The backend container reaches it via `http://host.docker.internal:11434`.

## Commands

Once the project is scaffolded, the expected commands are:

```bash
# Start the full stack (frontend + backend + Postgres)
docker-compose up

# Regenerate frontend types and hooks from the backend OpenAPI schema
# Run this whenever Pydantic models or routes change
cd frontend && npx orval

# Seed the database with mock data (25+ customers, 40-60 shipments)
cd backend && python scripts/seed_data.py

# Pull the LLM (run once on the host machine, outside Docker)
ollama pull qwen3:8b
```

## Data Model

```
Customer        → id, first_name, last_name, phone_number (E.164), address
Shipment        → id, customer_id (FK), tracking_number, status (enum), carrier, origin, destination, estimated_delivery, last_update
Package         → id, shipment_id (FK), description, weight_kg, declared_value
ChatSession     → id, customer_id (nullable FK), state (enum), started_at, ended_at, transcript (JSONB)
```

`ChatSession.transcript` is an array of `{role, content, timestamp, tool_calls?}` objects. Every turn must be persisted here — wire this from Week 1 before the flow gets complex.

`ChatSession.state` enum: `anonymous | collecting_identity | code_sent | awaiting_code | verified | escalated_to_human`

## Tool Definitions

The backend exposes these tools to Ollama on every chat request. The model requests them; the backend executes them after checking session state.

| Tool | When called | What backend does |
|---|---|---|
| `request_identity_info()` | Model wants to start collection | Transition state to `collecting_identity` |
| `verify_identity(first_name, last_name, address, phone_number)` | Model has collected all fields | Match against Customer table; on match → generate code, set `pending_customer_id`, transition to `code_sent` |
| `send_verification_code(customer_id)` | (internal, post-match) | Generate 6-digit code, log to console (mock SMS) |
| `lookup_shipments()` | Verified user asks about shipments | `SELECT * FROM shipments WHERE customer_id = session.customer_id` |

## Key Conventions

- **No hand-written TypeScript types or fetch calls.** Run `npx orval` after any backend schema change and commit the output.
- **Admin auth via Auth0 Agent Skills** (`npx skills add auth0/agent-skills`). Install before starting Epic E — not mid-way through.
- **Mock data only.** All customer/shipment/package data is synthetic. The seed script lives in `scripts/seed_data.py` and must be re-runnable.
- **Human escalation (Epic G) is purely cosmetic.** No backend logic beyond setting `state = escalated_to_human`. The fake "human" persona must still refuse to reveal shipment data to unverified sessions.
- **The 2FA modal appears on demand**, triggered by the backend signaling `code_sent` state — it is not pre-rendered on page load.
