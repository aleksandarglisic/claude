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
- **Auth (admin only):** Auth0 — JWKS-based RS256 JWT validation via `python-jose` (`auth/auth0.py`); `@auth0/auth0-react` on the frontend
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

# Run prompt injection defense tests (Epic F2)
docker-compose exec backend python scripts/test_prompt_injection.py

# Run identity-system separation guarantee tests (Epic E4)
docker-compose exec backend python scripts/test_separation.py

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
│   ├── routes/
│   │   ├── admin.py        # GET/POST/PUT/DELETE /admin/* — Auth0-protected CRUD (Epic E2/E3)
│   │   ├── chat.py         # POST /chat, GET /chat/{id}/state — Ollama loop, session state
│   │   └── verify.py       # POST /verify-code — 2FA code check endpoint
│   ├── tools/
│   │   ├── identity.py     # IDENTITY_TOOLS schemas + handlers (Epic B/C)
│   │   └── shipments.py    # SHIPMENT_TOOLS schemas + lookup/details handlers (Epic D/F)
│   ├── auth/
│   │   └── auth0.py            # JWKS-based JWT validation, require_admin dependency (Epic E)
│   ├── schemas/
│   │   └── admin.py            # Pydantic Create/Update/Response models for admin CRUD
│   └── scripts/
│       ├── seed_data.py
│       ├── test_prompt_injection.py  # Epic F2 gate proof — run without DB/Ollama
│       └── test_separation.py        # Epic E4 gate proof — 16 AST checks, no DB/Ollama needed
└── frontend/
    ├── orval.config.ts     # Points at localhost:8000/openapi.json
    └── src/
        ├── api/generated/  # Orval output — DO NOT hand-edit
        ├── components/
        │   ├── ChatWindow/   # Main chat UI + escalation theater
        │   ├── CodeModal/    # 2FA code entry modal (appears on code_sent state)
        │   └── AdminPanel/   # Auth0-protected admin panel (Epic E/E2/E3)
        │       ├── AdminPanel.tsx        # Tab nav, Auth0 auth, token wiring
        │       ├── CustomerManager.tsx   # Full CRUD for customers
        │       ├── ShipmentManager.tsx   # Full CRUD for shipments + packages
        │       └── Manager.module.css    # Shared table/form/badge styles
        └── lib/axiosInstance.ts  # Orval mutator; setTokenGetter() wires Auth0 JWT
```

## Data Model

```
Customer     → id (str/uuid), first_name, last_name, phone_number (E.164), address
Shipment     → id, customer_id (FK), tracking_number, status (enum), carrier,
               origin, destination, estimated_delivery, last_update
Package      → id, shipment_id (FK), description, weight_kg, declared_value
ChatSession  → id, customer_id (nullable FK), state (enum), started_at,
               ended_at, transcript (JSONB),
               pending_customer_id (str, nullable),
               verification_code (VARCHAR(6), nullable),
               code_expires_at (TIMESTAMPTZ, nullable),
               code_attempts (int, default 0)
```

`ChatSession.transcript` — array of `{role, content, timestamp, tool_calls?}` objects, one pair per exchange.  
`tool_calls` inner schema: `[{name: str, arguments: dict | {"_redacted": True}, result: dict}]` — `verify_identity` arguments are always redacted before persistence.  
`ChatSession.state` enum: `anonymous | collecting_identity | code_sent | awaiting_code | verified | escalated_to_human`  
`Shipment.status` enum: `label_created | in_transit | out_for_delivery | delivered | exception`

## Architecture Constraints

**Identity gate is enforced in the backend tool layer, not in the model's prompt.** The model calls tools; the backend decides whether to execute them based on `session.state`. Never move the check into the system prompt.

**Tool layer always uses `session.customer_id`**, never a customer ID supplied by the model or user. `lookup_shipments` takes no `customer_id` parameter.

**Escalated-but-verified sessions can access shipment data.** If a user completes verification and then escalates to human, `session.customer_id` is already set. Both `_tools_for_state()` and `handle_lookup_shipments()` permit `lookup_shipments` when `state == escalated_to_human AND customer_id IS NOT NULL`. Escalating before verification still blocks data access.

**Two identity systems that must never intersect:**
1. Conversational verification (`ChatSession.state`) — session-scoped, for end users only
2. Auth0 JWT — admin panel only

**Ollama stays on the host.** The backend reaches it via `http://host.docker.internal:11434`. Running Ollama in Docker loses Apple Metal GPU acceleration.

**Session history is loaded from the DB transcript**, not from client-supplied history. The DB is the source of truth for conversation context. `GET /chat/{session_id}/state` returns `{session_id, session_state, known_first_name, show_modal, messages[]}` — no LLM call; restores the full visible chat history, verified badge, and modal state on page refresh.

**qwen3:8b emits `<think>…</think>` reasoning tokens.** These are stripped from the reply before returning to the client via `_strip_thinking()` in `routes/chat.py`.

**System prompt is rebuilt on every tool-loop iteration** (`messages[0]` is updated each round) so state transitions are reflected in the same exchange without an extra round-trip.

## Tool Definitions (Week 2+)

| Tool | Parameters | What backend does |
|---|---|---|
| `request_identity_info()` | — | Transition state → `collecting_identity` |
| `verify_identity(first_name, last_name, address, phone_number)` | strings | Match Customer table; on match → generate 6-digit code, set `pending_customer_id`, state → `code_sent` |
| `send_verification_code(customer_id)` | string (ignored) | Generate new code, reset attempts, state → `code_sent`; log to console |
| `check_verification_code(code)` | string | Fallback for code typed in chat; same expiry/attempt enforcement as `/verify-code` |
| `lookup_shipments()` | — | `SELECT … WHERE customer_id = session.customer_id` with packages eager-loaded; only executes for `verified` or `escalated_to_human + customer_id` |
| `get_shipment_details(tracking_number)` | string | Same gate; `WHERE customer_id = session.customer_id AND tracking_number = X` — returns not-found if the tracking number belongs to another customer |

Tools are split across two files and offered selectively:
- `IDENTITY_TOOLS` (all 4 identity tools) — offered for every state
- `SHIPMENT_TOOLS` (`lookup_shipments` + `get_shipment_details`) — added only when `state == verified` or `state == escalated_to_human AND customer_id IS NOT NULL`

Code expiry: **10 minutes**. Max attempts: **3** before lockout (resend resets the counter).

## Key Conventions

- **No hand-written TypeScript types or fetch calls.** Run `npm run generate` from `frontend/` after any backend schema change and commit the output.
- **Admin auth via Auth0 JWT (python-jose JWKS).** `auth/auth0.py` exposes `require_admin` FastAPI dependency used on every `/admin/*` route. Frontend wires the token via `setTokenGetter(getAccessTokenSilently)` in `AdminPanel.tsx` so Orval-generated hooks attach `Authorization: Bearer <token>` automatically.
- **Mock data only.** Seed script at `backend/scripts/seed_data.py` is re-runnable and wipes existing data first.
- **Human escalation theater is frontend-driven.** The backend only sets `state = escalated_to_human` and returns `escalated: true`. The timed sequence (color shift, Melany enters, greeting) runs entirely in `ChatWindow.tsx`.
- **`show_modal` reflects final state, not just the transition.** This means the modal reappears correctly after a page refresh when `state` is `code_sent` or `awaiting_code`. A `suppressModal` flag in the frontend prevents jarring re-opens after the user deliberately closes it.
- **2FA modal appears on demand**, triggered by backend signalling `code_sent` state — not pre-rendered.
- **Address matching is fuzzy.** `_match_address()` in `tools/identity.py` requires house number + at least one meaningful street keyword. Tolerates missing zip code, state abbreviation, and partial input.
- **`verify_identity` arguments are redacted before transcript persistence.** Name, address, and phone number are replaced with `{"_redacted": True}` in the JSONB transcript — the outcome (`verified: true/false`) is all that needs to persist. Redaction happens in `routes/chat.py` just before the `db.commit()` call.
- **No file-based logging anywhere.** No `logging` module setup, `FileHandler`, or log config files. The only sensitive console output is the `[2FA CODE]` print in `tools/identity.py` (intentional mock-SMS substitute). Never add `logging.FileHandler` or structured log sinks that capture identity fields.
- **Prompt injection cannot bypass the identity gate.** The gate is `_can_access()` in `tools/shipments.py`, shared by both shipment handlers. A fabricated `session_id` creates a new `anonymous` row (`customer_id=None`); no prompt can change that. Proven by `scripts/test_prompt_injection.py` (9 cases, no DB/Ollama needed).
- **Session state is tab-scoped.** `sessionId` is stored in `sessionStorage` (not `localStorage`) — each new tab starts a fresh anonymous session (Epic D3). On page refresh within the same tab, `GET /chat/{id}/state` restores the full message history, verified badge, `knownFirstName`, and modal state without requiring a message.
- **Frontend requires `--build` after source changes.** The frontend Docker container has no volume mount — Vite's HMR only applies within a running container. Any change to frontend source files requires `docker-compose up --build` to take effect. Backend is exempt (uvicorn `--reload` + volume mount).
- **`verify.py` appends a synthetic assistant turn on successful 2FA.** Without it, the model's next turn sees history ending at "code has been sent" and re-asks for identity details. The synthetic turn `{"role": "assistant", "content": "Identity verified — you're all set!..."}` closes the loop.
- **Tool call history is replayed from transcript — with exceptions.** Identity tool calls (`request_identity_info`, `send_verification_code`, `check_verification_code`) are replayed as `{role: assistant, tool_calls}` + `{role: tool}` pairs so the model has state-transition context. Shipment tools (`lookup_shipments`, `get_shipment_details`) are NOT replayed (`_NO_REPLAY_TOOLS` in `routes/chat.py`) — their data changes when admins edit packages/status, so replaying a stale result causes the model to answer from old data. Omitting them forces a fresh DB query on every new question.
- **Admin panel backend schema lives in `backend/schemas/admin.py`.** Pydantic `Create/Update/Response` models for Customer, Shipment, and Package. Run `npm run generate` from `frontend/` after any schema change to keep Orval types in sync.
- **Auth0 env vars required to use the admin panel.** Copy `secureship/.env.example` to `secureship/.env` and fill in `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_AUDIENCE`. Add `http://localhost:3000/admin` to Allowed Callback URLs in the Auth0 dashboard.
- **Identity system separation is proven by `scripts/test_separation.py` (Epic E4).** 16 AST-based checks verify at the import/reference level that admin routes never touch `ChatSession`/`SessionState`/tools, and chat routes never touch `auth/`. Run without DB or Ollama. Fails loudly (exit 1) if any check breaks.
