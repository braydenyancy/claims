# Claims

Claim review workflow: Django + DRF + PostgreSQL API. Vue 3 frontend arrives in stage 3.

## Run

    docker compose up

API on http://localhost:8000/api/. Health: `GET /api/health/`.

Seeded logins (password `password`): `sam` (submitter), `rita` and `rob` (reviewers).

The worker registers submitted claims with the clearinghouse; its log shows every attempt. Knobs: CLEARINGHOUSE_MAX_ATTEMPTS, CLEARINGHOUSE_LEASE_SECONDS, CLEARINGHOUSE_POLL_SECONDS.

## Develop

    docker compose up -d postgres
    cd backend && uv sync && uv run pytest

## Layout

- `backend/` Django project and the `claims` app
- `vendor/` third-party code used as-is (the clearinghouse client)
- `vendor/clearinghouse.sqlite3` is the clearinghouse's own store, created at runtime and git-ignored
- `docs/` compliance program, decisions, workflows, specs, plans
  (`docs/policies`, `docs/procedures` and `docs/security` are placeholders)
