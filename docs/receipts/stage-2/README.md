# Stage 2 receipts

Recorded 2026-09-13 on branch `stage-2-clearinghouse`, HEAD `b242b92`. Compose
project `stage-2-clearinghouse` (the worktree directory's default name; shown
explicitly below with `-p` since that is what was actually run). Compose
commands ran from the repository root; the curl walk ran from a scratch
directory holding the cookie jar `./jar`.

## 1. Clean build from removed volumes

```
$ docker compose -p stage-2-clearinghouse down -v
 Container stage-2-clearinghouse-postgres-1 Stopping
 Container stage-2-clearinghouse-postgres-1 Stopped
 Container stage-2-clearinghouse-postgres-1 Removing
 Container stage-2-clearinghouse-postgres-1 Removed
 Network stage-2-clearinghouse_default Removing
 Volume stage-2-clearinghouse_pgdata Removing
 Volume stage-2-clearinghouse_pgdata Removed
 Network stage-2-clearinghouse_default Removed

$ docker compose -p stage-2-clearinghouse up --build -d
 Image stage-2-clearinghouse-worker Building
 Image stage-2-clearinghouse-api Building
 ...
 #12 [worker stage-0 5/8] RUN uv sync --frozen
 #12 CACHED
 #13 [worker stage-0 6/8] COPY backend/ /app/
 #13 DONE 0.9s
 #14 [worker stage-0 7/8] COPY vendor/ /app/vendor/
 #14 DONE 0.0s
 #15 [api stage-0 8/8] RUN chmod +x /app/entrypoint.sh
 #15 DONE 0.1s
 ...
 Image stage-2-clearinghouse-api Built
 Image stage-2-clearinghouse-worker Built
 Network stage-2-clearinghouse_default Creating
 Volume stage-2-clearinghouse_pgdata Creating
 Network stage-2-clearinghouse_default Created
 Volume stage-2-clearinghouse_pgdata Created
 Container stage-2-clearinghouse-postgres-1 Creating
 Container stage-2-clearinghouse-postgres-1 Created
 Container stage-2-clearinghouse-api-1 Creating
 Container stage-2-clearinghouse-api-1 Created
 Container stage-2-clearinghouse-worker-1 Creating
 Container stage-2-clearinghouse-worker-1 Created
 Container stage-2-clearinghouse-postgres-1 Starting
 Container stage-2-clearinghouse-postgres-1 Started
 Container stage-2-clearinghouse-postgres-1 Waiting
 Container stage-2-clearinghouse-postgres-1 Healthy
 Container stage-2-clearinghouse-api-1 Starting
 Container stage-2-clearinghouse-api-1 Started
 Container stage-2-clearinghouse-api-1 Waiting
 Container stage-2-clearinghouse-api-1 Healthy
 Container stage-2-clearinghouse-worker-1 Starting
 Container stage-2-clearinghouse-worker-1 Started

$ docker compose -p stage-2-clearinghouse ps
NAME                               IMAGE                          COMMAND                  SERVICE    CREATED          STATUS                    PORTS
stage-2-clearinghouse-api-1        stage-2-clearinghouse-api      "/app/entrypoint.sh …"   api        11 seconds ago   Up 8 seconds (healthy)    0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
stage-2-clearinghouse-postgres-1   postgres:17-alpine             "docker-entrypoint.s…"   postgres   12 seconds ago   Up 11 seconds (healthy)   0.0.0.0:5433->5432/tcp, [::]:5433->5432/tcp
stage-2-clearinghouse-worker-1     stage-2-clearinghouse-worker   "python manage.py ru…"   worker     11 seconds ago   Up 2 seconds
```

api healthy, worker running (the worker has no healthcheck of its own; it
depends on api's).

## 2. Migrate, seed, and the worker registering the seeded pending claim

The seed leaves one claim's registration PENDING on purpose (`Cascade Care`,
day 3) so boot proves the worker without any manual step:

```
$ docker compose -p stage-2-clearinghouse logs api | grep -E "Applying|users:|claims:"
api-1  |   Applying contenttypes.0001_initial... OK
api-1  |   Applying contenttypes.0002_remove_content_type_name... OK
api-1  |   Applying auth.0001_initial... OK
api-1  |   Applying auth.0002_alter_permission_name_max_length... OK
api-1  |   Applying auth.0003_alter_user_email_max_length... OK
api-1  |   Applying auth.0004_alter_user_username_opts... OK
api-1  |   Applying auth.0005_alter_user_last_login_null... OK
api-1  |   Applying auth.0006_require_contenttypes_0002... OK
api-1  |   Applying auth.0007_alter_validators_add_error_messages... OK
api-1  |   Applying auth.0008_alter_user_username_max_length... OK
api-1  |   Applying auth.0009_alter_user_last_name_max_length... OK
api-1  |   Applying auth.0010_alter_group_name_max_length... OK
api-1  |   Applying auth.0011_update_proxy_permissions... OK
api-1  |   Applying auth.0012_alter_user_first_name_max_length... OK
api-1  |   Applying claims.0001_initial... OK
api-1  |   Applying claims.0002_claim_claimevent... OK
api-1  |   Applying claims.0003_claimevent_immutable... OK
api-1  |   Applying claims.0004_registration... OK
api-1  |   Applying sessions.0001_initial... OK
api-1  | users: sam, rita, rob
api-1  | claims: 10 created

$ docker compose -p stage-2-clearinghouse logs worker
worker-1  | worker: gateway=VendorGateway poll=1.0s
worker-1  | 2026-09-13 18:36:20,458 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=PENDING attempt=1
worker-1  | 2026-09-13 18:36:24,471 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=DONE attempt=2
```

The seeded claim's first attempt came back `PENDING` (a rejection or a lost
timeout, retried with backoff — the log doesn't need to say which, `lookup`
covers both), the second attempt reached `DONE`.

## 3. Five claims submitted as `sam`, then five more

```
$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' \
    -d '{"username": "sam", "password": "password"}' localhost:8000/api/auth/login/
{"id":1,"username":"sam","role":"submitter"}
```

(Login needs no CSRF header — there is no session yet for `CsrfViewMiddleware`
to enforce against — and the response sets the `csrftoken` cookie every
following unsafe request reads out of the jar as `$CSRF`, same as stage 1.)

Five claims, created and submitted in a loop:

```
$ CSRF=$(awk '$6=="csrftoken"{v=$7} END{print v}' ./jar)
$ for i in 1 2 3 4 5; do
    resp=$(curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
      -d "{\"payer\": \"Acme Health\", \"service_date\": \"2026-09-0$i\", \"billed_amount\": \"$((100+i)).00\"}" \
      localhost:8000/api/claims/)
    id=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
    curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
      -d '{"action": "submit", "version": 0}' localhost:8000/api/claims/$id/transition/
  done
```

Five references came back: `CLM-DE7F6FE5CEE4EAA3`, `CLM-1602FEB46B342AFA`,
`CLM-A838A3E1AC6EDD80`, `CLM-24C3763262A4FC5C`, `CLM-65EF6E2C57FB0A08`, each
`SUBMITTED` with `registration.status: "pending"`.

```
$ sleep 15 && docker compose -p stage-2-clearinghouse logs worker | grep -E "registration|reaped"
worker-1  | 2026-09-13 18:36:20,458 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=PENDING attempt=1
worker-1  | 2026-09-13 18:36:24,471 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=DONE attempt=2
worker-1  | 2026-09-13 18:37:13,994 INFO claims.worker registration claim=CLM-DE7F6FE5CEE4EAA3 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:15,545 INFO claims.worker registration claim=CLM-1602FEB46B342AFA status=DONE attempt=1
worker-1  | 2026-09-13 18:37:17,544 INFO claims.worker registration claim=CLM-A838A3E1AC6EDD80 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:18,745 INFO claims.worker registration claim=CLM-24C3763262A4FC5C status=DONE attempt=1
worker-1  | 2026-09-13 18:37:20,328 INFO claims.worker registration claim=CLM-65EF6E2C57FB0A08 status=DONE attempt=1
```

All five landed `DONE` on the first attempt — no retry or reconcile this
time, which the 25% failure rate on five independent rolls makes plausible
(`0.75^5 ≈ 24%` chance of zero failures). Submitting five more:

```
$ for i in 6 7 8 9 10; do
    resp=$(curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
      -d "{\"payer\": \"Blue Ridge Mutual\", \"service_date\": \"2026-09-0$((i-5))\", \"billed_amount\": \"$((200+i)).00\"}" \
      localhost:8000/api/claims/)
    id=$(echo "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
    curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
      -d '{"action": "submit", "version": 0}' localhost:8000/api/claims/$id/transition/
  done
```

References: `CLM-F0990C1581D6A5E4`, `CLM-2EFFB445B897A14B`,
`CLM-96218D26EADB0D33`, `CLM-B7EF67EBAA7ECF10`, `CLM-8926E3021B76C56A`.

```
$ sleep 15 && docker compose -p stage-2-clearinghouse logs worker | grep -E "registration|reaped"
worker-1  | 2026-09-13 18:36:20,458 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=PENDING attempt=1
worker-1  | 2026-09-13 18:36:24,471 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=DONE attempt=2
worker-1  | 2026-09-13 18:37:13,994 INFO claims.worker registration claim=CLM-DE7F6FE5CEE4EAA3 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:15,545 INFO claims.worker registration claim=CLM-1602FEB46B342AFA status=DONE attempt=1
worker-1  | 2026-09-13 18:37:17,544 INFO claims.worker registration claim=CLM-A838A3E1AC6EDD80 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:18,745 INFO claims.worker registration claim=CLM-24C3763262A4FC5C status=DONE attempt=1
worker-1  | 2026-09-13 18:37:20,328 INFO claims.worker registration claim=CLM-65EF6E2C57FB0A08 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:38,818 INFO claims.worker registration claim=CLM-F0990C1581D6A5E4 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:40,629 INFO claims.worker registration claim=CLM-2EFFB445B897A14B status=DONE attempt=1
worker-1  | 2026-09-13 18:37:41,917 INFO claims.worker registration claim=CLM-96218D26EADB0D33 status=PENDING attempt=1
worker-1  | 2026-09-13 18:37:42,324 INFO claims.worker registration claim=CLM-B7EF67EBAA7ECF10 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:44,128 INFO claims.worker registration claim=CLM-8926E3021B76C56A status=DONE attempt=1
worker-1  | 2026-09-13 18:37:45,925 INFO claims.worker registration claim=CLM-96218D26EADB0D33 status=DONE attempt=2
```

`CLM-96218D26EADB0D33` (claim id 18) came back `PENDING` on attempt 1 and
`DONE` on attempt 2 — the retry this receipt is looking for.

## 4. History for the claim that retried

```
$ curl -s -b ./jar localhost:8000/api/claims/18/history/
[{"id":53,"action":"create","from_state":"DRAFT","to_state":"DRAFT","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T18:37:37.316137Z"},
 {"id":54,"action":"submit","from_state":"DRAFT","to_state":"SUBMITTED","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T18:37:37.379862Z"},
 {"id":61,"action":"registration_retry","from_state":"SUBMITTED","to_state":"SUBMITTED","actor":null,"data":{"reason":"Service unavailable","attempt":1,"retry_in_seconds":2},"severity":"warning","created_at":"2026-09-13T18:37:41.910595Z"},
 {"id":64,"action":"registration_succeeded","from_state":"SUBMITTED","to_state":"SUBMITTED","actor":null,"data":{"attempt":2,"submission_id":"CH-37CB3F0C82"},"severity":"info","created_at":"2026-09-13T18:37:45.920462Z"}]
```

## 5. Alert lifecycle as `rita`

The seed's FAILED claim (`Cascade Care`, `$510.00`, 5 exhausted attempts) is
the only one with an open alert:

```
$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"username": "rita", "password": "password"}' localhost:8000/api/auth/login/
{"id":2,"username":"rita","role":"reviewer"}

$ curl -s -b ./jar "localhost:8000/api/claims/?alert=open"
{"count":1,"next":null,"previous":null,"results":[{"id":10,"reference":"CLM-1759526569253140","payer":"Cascade Care","service_date":"2026-08-10","billed_amount":"510.00","state":"SUBMITTED","version":1,"has_open_alert":true,"created_by":"sam","created_at":"2026-09-13T18:36:13.987692Z","updated_at":"2026-09-13T18:36:13.988398Z"}]}

$ curl -s -b ./jar localhost:8000/api/claims/10/
{"id":10,"reference":"CLM-1759526569253140","payer":"Cascade Care","service_date":"2026-08-10","billed_amount":"510.00","state":"SUBMITTED","version":1,"has_open_alert":true,"created_by":"sam","created_at":"2026-09-13T18:36:13.987692Z","updated_at":"2026-09-13T18:36:13.988398Z","approved_amount":null,"denial_reason":"","submission_id":"","available_actions":[{"action":"start_review","label":"Start review","fields":[],"blocked_reason":"Claim has no clearinghouse submission ID yet."}],"registration":{"status":"failed","attempts":5,"last_error":"Service unavailable","submission_id":"","next_attempt_at":null}}
```

Retry it:

```
$ CSRF=$(awk '$6=="csrftoken"{v=$7} END{print v}' ./jar)
$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -X POST localhost:8000/api/claims/10/registration/retry/
{"id":10,"reference":"CLM-1759526569253140","payer":"Cascade Care","service_date":"2026-08-10","billed_amount":"510.00","state":"SUBMITTED","version":1,"has_open_alert":true,"created_by":"sam","created_at":"2026-09-13T18:36:13.987692Z","updated_at":"2026-09-13T18:36:13.988398Z","approved_amount":null,"denial_reason":"","submission_id":"","available_actions":[{"action":"start_review","label":"Start review","fields":[],"blocked_reason":"Claim has no clearinghouse submission ID yet."}],"registration":{"status":"pending","attempts":0,"last_error":"","submission_id":"","next_attempt_at":"2026-09-13T18:38:23.630165+00:00"}}

$ sleep 5 && docker compose -p stage-2-clearinghouse logs worker | grep "CLM-1759526569253140"
worker-1  | 2026-09-13 18:38:24,745 INFO claims.worker registration claim=CLM-1759526569253140 status=DONE attempt=1
```

The retry landed `DONE` on the first attempt. Its history now carries the
original alert (`id 31`) plus the retry and the success:

```
$ curl -s -b ./jar localhost:8000/api/claims/10/history/
[{"id":29,"action":"create","from_state":"DRAFT","to_state":"DRAFT","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T18:36:13.987875Z"},
 {"id":30,"action":"submit","from_state":"DRAFT","to_state":"SUBMITTED","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T18:36:13.988632Z"},
 {"id":31,"action":"registration_failed","from_state":"SUBMITTED","to_state":"SUBMITTED","actor":null,"data":{"reason":"Service unavailable","attempts":5},"severity":"alert","created_at":"2026-09-13T18:36:13.989426Z"},
 {"id":65,"action":"registration_retry_requested","from_state":"SUBMITTED","to_state":"SUBMITTED","actor":"rita","data":{},"severity":"info","created_at":"2026-09-13T18:38:23.630775Z"},
 {"id":66,"action":"registration_succeeded","from_state":"SUBMITTED","to_state":"SUBMITTED","actor":null,"data":{"attempt":1,"submission_id":"CH-631F055257"},"severity":"info","created_at":"2026-09-13T18:38:24.744159Z"}]
```

Acknowledge the alert (event 31) with a note:

```
$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"event_id": 31, "note": "Confirmed at the clearinghouse: retried and now registered as CH-631F055257. No duplicate billing."}' \
    localhost:8000/api/claims/10/acknowledge/
{"id":10,"reference":"CLM-1759526569253140","payer":"Cascade Care","service_date":"2026-08-10","billed_amount":"510.00","state":"SUBMITTED","version":1,"has_open_alert":false,"created_by":"sam","created_at":"2026-09-13T18:36:13.987692Z","updated_at":"2026-09-13T18:38:39.367094Z","approved_amount":null,"denial_reason":"","submission_id":"CH-631F055257","available_actions":[{"action":"start_review","label":"Start review","fields":[],"blocked_reason":null}],"registration":{"status":"done","attempts":1,"last_error":"","submission_id":"CH-631F055257","next_attempt_at":null}}
```

`has_open_alert` is now `false` and `start_review` is unblocked (its
`blocked_reason` dropped to `null`) — nothing was cleared from the history,
the acknowledgement just answered the alert already on the record.

## 6. Whole run's outcomes in one place, then teardown

```
$ docker compose -p stage-2-clearinghouse logs worker | grep -E "registration|reaped"
worker-1  | 2026-09-13 18:36:20,458 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=PENDING attempt=1
worker-1  | 2026-09-13 18:36:24,471 INFO claims.worker registration claim=CLM-ED04F1D46073277D status=DONE attempt=2
worker-1  | 2026-09-13 18:37:13,994 INFO claims.worker registration claim=CLM-DE7F6FE5CEE4EAA3 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:15,545 INFO claims.worker registration claim=CLM-1602FEB46B342AFA status=DONE attempt=1
worker-1  | 2026-09-13 18:37:17,544 INFO claims.worker registration claim=CLM-A838A3E1AC6EDD80 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:18,745 INFO claims.worker registration claim=CLM-24C3763262A4FC5C status=DONE attempt=1
worker-1  | 2026-09-13 18:37:20,328 INFO claims.worker registration claim=CLM-65EF6E2C57FB0A08 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:38,818 INFO claims.worker registration claim=CLM-F0990C1581D6A5E4 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:40,629 INFO claims.worker registration claim=CLM-2EFFB445B897A14B status=DONE attempt=1
worker-1  | 2026-09-13 18:37:41,917 INFO claims.worker registration claim=CLM-96218D26EADB0D33 status=PENDING attempt=1
worker-1  | 2026-09-13 18:37:42,324 INFO claims.worker registration claim=CLM-B7EF67EBAA7ECF10 status=DONE attempt=1
worker-1  | 2026-09-13 18:37:44,128 INFO claims.worker registration claim=CLM-8926E3021B76C56A status=DONE attempt=1
worker-1  | 2026-09-13 18:37:45,925 INFO claims.worker registration claim=CLM-96218D26EADB0D33 status=DONE attempt=2
worker-1  | 2026-09-13 18:38:24,745 INFO claims.worker registration claim=CLM-1759526569253140 status=DONE attempt=1
```

The log covers twelve distinct references across fourteen registration
attempts: ten reached `DONE` on the only attempt shown for them —
including `CLM-1759526569253140`, the retried `FAILED` seed claim, whose
single line here is its post-acknowledgement retry rather than a fresh
submission — and two claims (`CLM-ED04F1D46073277D`, the seed's original
registration; `CLM-96218D26EADB0D33`, the eighth freshly submitted claim,
id 18) needed one retry each, going `PENDING` on attempt 1 before `DONE`
on attempt 2. No `reaped` line, since no lease ever expired.

```
$ docker compose -p stage-2-clearinghouse down
 Container stage-2-clearinghouse-worker-1 Stopping
 Container stage-2-clearinghouse-worker-1 Stopped
 Container stage-2-clearinghouse-worker-1 Removing
 Container stage-2-clearinghouse-worker-1 Removed
 Container stage-2-clearinghouse-api-1 Stopping
 Container stage-2-clearinghouse-api-1 Stopped
 Container stage-2-clearinghouse-api-1 Removing
 Container stage-2-clearinghouse-api-1 Removed
 Container stage-2-clearinghouse-postgres-1 Stopping
 Container stage-2-clearinghouse-postgres-1 Stopped
 Container stage-2-clearinghouse-postgres-1 Removing
 Container stage-2-clearinghouse-postgres-1 Removed
 Network stage-2-clearinghouse_default Removing
 Network stage-2-clearinghouse_default Removed

$ docker compose -p stage-2-clearinghouse up -d postgres
 Network stage-2-clearinghouse_default Creating
 Network stage-2-clearinghouse_default Created
 Container stage-2-clearinghouse-postgres-1 Creating
 Container stage-2-clearinghouse-postgres-1 Created
 Container stage-2-clearinghouse-postgres-1 Starting
 Container stage-2-clearinghouse-postgres-1 Started
```

## Tests

```
$ cd backend && uv run pytest -q
........................................................................ [ 37%]
........................................................................ [ 75%]
..............................................                           [100%]
190 passed in 36.93s
```

(187 at the tip of task 5's work, `e2b4f51`; 190 here because a fix commit,
`b242b92`, landed on the branch mid-session and added tests of its own —
unrelated to this task's four files.)
