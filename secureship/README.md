# SecureShip

AI-gated shipment support chat. Customers verify their identity conversationally with a locally-run LLM before getting access to their shipment data. No traditional login for end users.

## Prerequisites

- Docker Desktop for Mac
- Ollama installed on the host (`brew install ollama` or [ollama.com](https://ollama.com/download/mac))
- Node.js 22+ (for Orval codegen)

## Run

```bash
# Pull the LLM once (host machine, outside Docker)
ollama pull qwen3:8b

# Start frontend + backend + Postgres
docker-compose up
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Regenerate frontend types

Run this after any Pydantic model or route change:

```bash
cd frontend && npm run generate
```

## Seed mock data

```bash
docker-compose exec backend python scripts/seed_data.py
```
