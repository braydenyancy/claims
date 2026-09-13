# Stage 1 receipts

Recorded 2026-09-13 on branch `stage-1-backend-core`. Every command was run from
the repository root; the curl walk ran from a scratch directory holding the cookie
jar `./jar`.

## 1. Clean build from removed volumes

```
$ docker compose down -v
 Container stage-1-backend-core-api-1 Stopping 
 Container stage-1-backend-core-api-1 Stopped 
 Container stage-1-backend-core-api-1 Removing 
 Container stage-1-backend-core-api-1 Removed 
 Container stage-1-backend-core-postgres-1 Stopping 
 Container stage-1-backend-core-postgres-1 Stopped 
 Container stage-1-backend-core-postgres-1 Removing 
 Container stage-1-backend-core-postgres-1 Removed 
 Volume stage-1-backend-core_pgdata Removing 
 Network stage-1-backend-core_default Removing 
 Volume stage-1-backend-core_pgdata Removed 
 Network stage-1-backend-core_default Removed 

$ docker compose up --build -d
 Image stage-1-backend-core-api Building 
 Image stage-1-backend-core-api Built 
 Volume stage-1-backend-core_pgdata Creating 
 Volume stage-1-backend-core_pgdata Creating 
 Network stage-1-backend-core_default Creating 
 Network stage-1-backend-core_default Creating 
 Volume stage-1-backend-core_pgdata Created 
 Volume stage-1-backend-core_pgdata Created 
 Network stage-1-backend-core_default Created 
 Network stage-1-backend-core_default Created 
 Container stage-1-backend-core-postgres-1 Creating 
 Container stage-1-backend-core-postgres-1 Created 
 Container stage-1-backend-core-api-1 Creating 
 Container stage-1-backend-core-api-1 Created 
 Container stage-1-backend-core-postgres-1 Starting 
 Container stage-1-backend-core-postgres-1 Started 
 Container stage-1-backend-core-postgres-1 Waiting 
 Container stage-1-backend-core-postgres-1 Healthy 
 Container stage-1-backend-core-api-1 Starting 
 Container stage-1-backend-core-api-1 Started 
```

## 2. Migrate and seed, from `docker compose logs api`

```
$ docker compose logs api | grep -E "Operations to perform|Apply all migrations|Running migrations|Applying claims|users:|claims:"
api-1  | Operations to perform:
api-1  |   Apply all migrations: auth, claims, contenttypes, sessions
api-1  | Running migrations:
api-1  |   Applying claims.0001_initial... OK
api-1  |   Applying claims.0002_claim_claimevent... OK
api-1  |   Applying claims.0003_claimevent_immutable... OK
api-1  | users: sam, rita, rob
api-1  | claims: 9 created

$ curl -s localhost:8000/api/health/
{"status":"ok","database":"ok"}
```

## 3. Lifecycle walk with a cookie jar

Every unsafe request carries `-c ./jar -b ./jar` and the `X-CSRFToken` header read
back out of the jar (`awk '$6=="csrftoken"{v=$7} END{print v}' ./jar`), shown below
as `$CSRF`. The submission ID is stamped on directly: stage 1 has no clearinghouse
worker, and `start_review` requires the ID.

```
$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"username": "sam", "password": "password"}' localhost:8000/api/auth/login/
{"id":1,"username":"sam","role":"submitter"}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"payer": "Acme Health", "service_date": "2026-09-01", "billed_amount": "100.00"}' localhost:8000/api/claims/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"DRAFT","version":0,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:49.427070Z","approved_amount":null,"denial_reason":"","submission_id":"","available_actions":[{"action":"submit","label":"Submit","fields":[],"blocked_reason":null},{"action":"withdraw","label":"Withdraw","fields":[],"blocked_reason":null}],"registration":{"status":"not_submitted"}}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"action": "submit", "version": 0}' localhost:8000/api/claims/10/transition/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"SUBMITTED","version":1,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:49.514645Z","approved_amount":null,"denial_reason":"","submission_id":"","available_actions":[],"registration":{"status":"pending"}}

$ docker compose exec api python manage.py shell -c "from claims.models import Claim; Claim.objects.filter(pk=10).update(submission_id='CH-WALK000001')"
7 objects imported automatically (use -v 2 for details).


$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"username": "rita", "password": "password"}' localhost:8000/api/auth/login/
{"id":2,"username":"rita","role":"reviewer"}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"action": "start_review", "version": 1}' localhost:8000/api/claims/10/transition/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"UNDER_REVIEW","version":2,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:50.479208Z","approved_amount":null,"denial_reason":"","submission_id":"CH-WALK000001","available_actions":[{"action":"request_info","label":"Request info","fields":[{"name":"note","type":"text","choices":[]}],"blocked_reason":null},{"action":"approve","label":"Approve","fields":[{"name":"approved_amount","type":"decimal","choices":[]}],"blocked_reason":null},{"action":"deny","label":"Deny","fields":[{"name":"denial_reason","type":"choice","choices":["not_covered","duplicate","insufficient_documentation","out_of_network","timely_filing"]}],"blocked_reason":null}],"registration":{"status":"registered","submission_id":"CH-WALK000001"}}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"action": "request_info", "version": 2, "data": {"note": "Please attach the operative report."}}' localhost:8000/api/claims/10/transition/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"INFO_REQUESTED","version":3,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:50.505626Z","approved_amount":null,"denial_reason":"","submission_id":"CH-WALK000001","available_actions":[],"registration":{"status":"registered","submission_id":"CH-WALK000001"}}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"username": "sam", "password": "password"}' localhost:8000/api/auth/login/
{"id":1,"username":"sam","role":"submitter"}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"action": "provide_info", "version": 3, "data": {"note": "Report attached."}}' localhost:8000/api/claims/10/transition/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"UNDER_REVIEW","version":4,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:50.665792Z","approved_amount":null,"denial_reason":"","submission_id":"CH-WALK000001","available_actions":[],"registration":{"status":"registered","submission_id":"CH-WALK000001"}}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"username": "rita", "password": "password"}' localhost:8000/api/auth/login/
{"id":2,"username":"rita","role":"reviewer"}

$ curl -s -c ./jar -b ./jar -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" \
    -d '{"action": "approve", "version": 4, "data": {"approved_amount": "50.50"}}' localhost:8000/api/claims/10/transition/
{"id":10,"reference":"CLM-3362F7768B6BBFFC","payer":"Acme Health","service_date":"2026-09-01","billed_amount":"100.00","state":"APPROVED","version":5,"created_by":"sam","created_at":"2026-09-13T02:18:49.427063Z","updated_at":"2026-09-13T02:18:50.828948Z","approved_amount":"50.50","denial_reason":"","submission_id":"CH-WALK000001","available_actions":[],"registration":{"status":"registered","submission_id":"CH-WALK000001"}}

$ curl -s -b ./jar localhost:8000/api/claims/10/history/
[{"id":24,"action":"create","from_state":"DRAFT","to_state":"DRAFT","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T02:18:49.428079Z"},{"id":25,"action":"submit","from_state":"DRAFT","to_state":"SUBMITTED","actor":"sam","data":{},"severity":"info","created_at":"2026-09-13T02:18:49.515283Z"},{"id":26,"action":"start_review","from_state":"SUBMITTED","to_state":"UNDER_REVIEW","actor":"rita","data":{},"severity":"info","created_at":"2026-09-13T02:18:50.479730Z"},{"id":27,"action":"request_info","from_state":"UNDER_REVIEW","to_state":"INFO_REQUESTED","actor":"rita","data":{"note":"Please attach the operative report."},"severity":"info","created_at":"2026-09-13T02:18:50.506149Z"},{"id":28,"action":"provide_info","from_state":"INFO_REQUESTED","to_state":"UNDER_REVIEW","actor":"sam","data":{"note":"Report attached."},"severity":"info","created_at":"2026-09-13T02:18:50.666301Z"},{"id":29,"action":"approve","from_state":"UNDER_REVIEW","to_state":"APPROVED","actor":"rita","data":{"approved_amount":"50.50"},"severity":"info","created_at":"2026-09-13T02:18:50.829440Z"}]
```

## 4. Stack down, postgres back up for the test runs

```
$ docker compose down
 Container stage-1-backend-core-api-1 Stopping 
 Container stage-1-backend-core-api-1 Stopped 
 Container stage-1-backend-core-api-1 Removing 
 Container stage-1-backend-core-api-1 Removed 
 Container stage-1-backend-core-postgres-1 Stopping 
 Container stage-1-backend-core-postgres-1 Stopped 
 Container stage-1-backend-core-postgres-1 Removing 
 Container stage-1-backend-core-postgres-1 Removed 
 Network stage-1-backend-core_default Removing 
 Network stage-1-backend-core_default Removed 

$ docker compose up -d postgres
 Network stage-1-backend-core_default Creating 
 Network stage-1-backend-core_default Creating 
 Network stage-1-backend-core_default Created 
 Network stage-1-backend-core_default Created 
 Container stage-1-backend-core-postgres-1 Creating 
 Container stage-1-backend-core-postgres-1 Created 
 Container stage-1-backend-core-postgres-1 Starting 
 Container stage-1-backend-core-postgres-1 Started 
```
