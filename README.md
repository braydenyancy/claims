# Claims

Django REST Framework, PostgreSQL, and Vue 3 claim review demo. See [NOTES.md](NOTES.md) for assumptions, design choices, and limitations, and `docs/` for the architecture, decisions, and compliance notes.

## Run

```sh
docker compose up
```

Open http://localhost:5173. The API is at http://localhost:8000/api/ and its health endpoint is `/api/health/`. First startup builds the images, migrates the database, and seeds sample claims. Sign in as `sam` (submitter), `rita`, or `rob` (reviewers); the demo password is `password`. Historical `CH-SEED` IDs are fixtures; new submissions use the worker.

The worker registers newly submitted claims in the background. Its activity is visible with `docker compose logs -f worker`.

A read-only admin at http://localhost:8000/admin/ shows every claim, event, and registration row. Sign in as `admin` / `password`.

## Run locally

Postgres stays in Docker; the API and frontend run on the host.

```sh
docker compose up -d postgres
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py seed
uv run python manage.py runserver          # http://localhost:8000
uv run python manage.py run_worker         # second terminal
cd frontend && npm install && npm run dev  # http://localhost:5173, proxies /api to :8000
```

Seeded users and a live walkthrough are in [docs/SEED.md](docs/SEED.md).

## Test

With the stack running:

```sh
docker compose exec api pytest
docker compose exec frontend npm run typecheck
docker compose exec frontend npm test
```
