# Stage 2 walkthrough: clearinghouse registration

Four files carry the design. Read them in this order.

## 1. The gateway: `backend/claims/clearinghouse/gateway.py`

`VendorGateway` is the only code in the repository that imports the
vendor module, and it does so lazily inside its two methods. Its whole
job is to turn the vendor's two exceptions into three explicit values:
`Registered` (we have an ID), `Rejected` (nothing was recorded, retry is
safe), and `Unknown` (something may have been recorded, never retry
blind). That third value is the point. An exception is easy to catch
and retry in a hurry; a named outcome forces the caller to handle "maybe"
as a case.

`register` runs the vendor call under a client-side timeout well under
the lease, and reports a timeout as `Unknown`. `FakeGateway` mirrors the
vendor's recording rules for tests, including the one the design rests
on: a timeout leaves a record behind.

## 2. The worker: `backend/claims/clearinghouse/worker.py`

Four functions, and the transaction boundaries are the design.

- `claim_next` opens one short transaction: take the next due PENDING
  row with `SELECT ... FOR UPDATE SKIP LOCKED`, mark it IN_FLIGHT with a
  fresh lease token, commit. Two workers get different rows.
- `process` opens no transaction. It always calls `lookup` before
  `register`. One existing ID is adopted; more than one halts with an
  alert; none means register. On `Unknown` it looks up again at once.
- `record` opens one short transaction, locks the claim then the
  registration, and writes the outcome, the claim, and the audit event
  together, but only if the lease token still matches. A late result
  from a worker that outlived its lease is discarded and logged as a
  warning event.
- `reap` returns expired leases to PENDING. Their next attempt looks up
  first, so anything the dead worker actually sent is adopted, not sent
  again.

The sentence to say cold: the vendor is never called inside a database
transaction, and it is never called without a lookup first. There is a
test that asserts the first half by making the fake gateway refuse to
run inside an open transaction.

## 3. The one window: NOTES.md, stage 2

If a vendor call outlives its lease, a second worker can look up before
the first worker's record lands, and both may submit. The lease token
protects the write, not the call. The client-side timeout keeps every
call under the lease, so the window needs a vendor outage longer than
the lease to open. Closing it fully needs an idempotency key on the
vendor's side, which this vendor does not offer. That is the honest
answer to "can this ever double bill", and it is written down before
anyone asks.

## 4. The alert lifecycle: `services.retry_registration` and `services.acknowledge_alert`

Alerts are a severity on events plus a flag on the claim. A reviewer can
retry a FAILED registration, which is an event; HALTED is not retryable
through the API because a human has to resolve it at the clearinghouse.
Acknowledging an alert requires a note and is itself an event; nothing
is ever cleared, and the flag drops only when every alert has an
answer. A successful retry leaves the alert open on purpose until a
reviewer answers it.

## Interleaving table

| interleaving | result |
|---|---|
| worker dies after the vendor call returns, before recording | reaped; next attempt's lookup finds the orphaned ID; adopted |
| worker dies before the vendor call | reaped; lookup finds nothing; registers once; the attempt still counts |
| two workers start together | `SKIP LOCKED` hands each a different row; proven with real threads |
| timeout where the vendor records late | immediate second lookup misses; retry scheduled; the next attempt's lookup adopts |
| reviewer retries a registration whose last attempt actually recorded | the API makes no vendor call; the worker looks up first and adopts |
| vendor call outlives its lease and a second worker claims the row | the one open window; bounded by the call timeout; closable only with a vendor idempotency key |

The receipts under `docs/receipts/stage-2/` reproduce the first row
deterministically: a dead worker's lost result is adopted, and the
vendor's own store shows exactly one record before and after.

## What review caught before the interview would have

- Retrying a claim with no registration row (any draft) returned a 500.
- The worker recorded outcomes with a lock order opposite to the API's
  retry path, which Postgres would have resolved by killing one of them.
- The worker had no restart policy and no exception guard, so one
  unmapped error would have stopped registration silently.
- Nothing bounded the vendor call's duration against the lease.

## Likely live-session extensions

- **Switch the vendor to an HTTP client.** Touches `VendorGateway` and
  one settings key. The outcome types, the worker, and every test stay
  as they are. The one real edit: map the HTTP client's timeout to
  `Unknown` and its connection errors to `Rejected`.
- **Add a second outbox consumer, such as a notification on
  `request_info`.** Enqueuing is one line in `SIDE_EFFECTS`. Consuming
  is a copy of the worker today; the honest answer is that the
  lease-and-retry machinery is generic apart from the model reference,
  and the refactor is an abstract outbox base with `run_worker
  --queue=<name>`. Naming that seam is a better answer than claiming it
  is already one line.
