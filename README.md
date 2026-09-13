# Claims

Claim review workflow: Django + DRF + PostgreSQL API, Vue 3 frontend.

## Run

    docker compose up

API on http://localhost:8000/api/. Health: `GET /api/health/`.

Seeded logins (password `password`): `sam` (submitter), `rita` and `rob` (reviewers).

## Develop

    docker compose up -d postgres
    cd backend && uv sync && uv run pytest

## Layout

- `backend/` Django project and the `claims` app
- `vendor/` third-party code used as-is (the clearinghouse client)
- `docs/` compliance program, decisions, workflows, specs, plans
