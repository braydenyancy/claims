# Claims

Django REST Framework, PostgreSQL, and Vue 3 claim review demo. See [NOTES.md](NOTES.md) for assumptions, design choices, and limitations.

## Run

```sh
docker compose up
```

Open http://localhost:5173. The API is at http://localhost:8000/api/ and its health endpoint is `/api/health/`. First startup builds the images, migrates the database, and seeds sample claims. Sign in as `sam` (submitter), `rita`, or `rob` (reviewers); the demo password is `password`. Historical `CH-SEED` IDs are fixtures; new submissions use the worker.

The worker registers newly submitted claims in the background. Its activity is visible with `docker compose logs -f worker`.

## Test

With the stack running:

```sh
docker compose exec api pytest
docker compose exec frontend npm run typecheck
docker compose exec frontend npm test
```
