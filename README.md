# Claims

Claim review workflow: Django + DRF + PostgreSQL API, a registration
worker, and a Vue 3 frontend. Built for the Ortho Med senior fullstack
exercise. Start with `NOTES.md`; `docs/walkthroughs/` gives the reading
order for each stage.

## Run

    docker compose up

The first start builds the API image and installs frontend packages,
which takes a minute or two; later starts are seconds. Then:

- UI on http://localhost:5173 (the Vite dev server proxies `/api` to the API)
- API on http://localhost:8000/api/ (health: `GET /api/health/`)

Seeded logins, password `password`: `sam` (submitter), `rita` and `rob`
(reviewers). The seed includes claims in every state, one whose
registration the worker completes on boot, and one whose registration
failed with an open alert.

The worker registers submitted claims with the clearinghouse; its log
shows every attempt (`docker compose logs -f worker`). Knobs:
`CLEARINGHOUSE_MAX_ATTEMPTS`, `CLEARINGHOUSE_LEASE_SECONDS`,
`CLEARINGHOUSE_POLL_SECONDS`, `CLEARINGHOUSE_CALL_TIMEOUT_SECONDS`.

## Tests

    docker compose up -d postgres
    cd backend && uv sync && uv run pytest          # 200 tests
    cd frontend && npm install && npm run typecheck && npm test   # 20 tests

What each test file proves is described in `NOTES.md` and at the top of
the file itself.

## Develop

    docker compose up -d postgres api
    cd frontend && npm install && npm run dev

## Layout

- `backend/` Django project and the `claims` app
- `frontend/` Vue 3 app
- `vendor/` third-party code used as-is (the clearinghouse client);
  `vendor/clearinghouse.sqlite3` is its own store, created at runtime and git-ignored
- `docs/` compliance program, decisions, workflows, specs, plans, receipts, walkthroughs
  (`docs/policies`, `docs/procedures` and `docs/security` are placeholders)
