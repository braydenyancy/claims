# Claims

Claim review workflow: Django + DRF + PostgreSQL API. Vue 3 frontend arrives in stage 3.

## Run

    docker compose up

API on http://localhost:8000/api/. Health: `GET /api/health/`.
UI on http://localhost:5173 (the Vite dev server proxies /api to the API).

Seeded logins (password `password`): `sam` (submitter), `rita` and `rob` (reviewers).

The worker registers submitted claims with the clearinghouse; its log shows every attempt. Knobs: CLEARINGHOUSE_MAX_ATTEMPTS, CLEARINGHOUSE_LEASE_SECONDS, CLEARINGHOUSE_POLL_SECONDS.

## Develop

    docker compose up -d postgres
    cd backend && uv sync && uv run pytest

    cd frontend && npm install && npm run dev  # with the API running under compose
    npm run typecheck && npm test

## Layout

- `backend/` Django project and the `claims` app
- `frontend/` Vue 3 app
- `vendor/` third-party code used as-is (the clearinghouse client)
- `vendor/clearinghouse.sqlite3` is the clearinghouse's own store, created at runtime and git-ignored
- `docs/` compliance program, decisions, workflows, specs, plans
  (`docs/policies`, `docs/procedures` and `docs/security` are placeholders)
