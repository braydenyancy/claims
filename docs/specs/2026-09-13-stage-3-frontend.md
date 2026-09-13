# Stage 3: Frontend

Status: complete. Decisions: D3, D4 (the UI renders actions, never
decides them), D5, D11. Workflows: W1, W2, W3, W6.

## Goal

A Vue 3 app a reviewer can trust: log in, find a claim, see exactly what
they may do to it, do it, and see what happened. Every rule lives on the
server; the UI renders the API's answers and its errors.

## Out of scope

Visual polish. Registration, SSO. Real-time push (polling is enough).
Pagination controls beyond "next page". Production build and serving
(the Vite dev server behind compose is the deliverable).

## Stack and shape

Vue 3 with the Composition API and TypeScript, Vite, vue-router. No
Pinia: one composable holds the session. No component library. Vitest
with Vue Test Utils for the handful of logic that deserves a test.

The dev server proxies `/api` to the API container, so the browser and
the API share an origin: the session cookie is first-party, CSRF is one
header read from the cookie, and CORS never comes up. Compose gains a
`frontend` service on port 5173.

## Screens

| route | shows | does |
|---|---|---|
| `/login` | username, password, error | POST login, then go to `/claims` |
| `/claims` | list with reference, payer, state, amount, updated; filters: state, open alerts; "new draft" form | GET list with filters; POST draft, then go to its detail |
| `/claims/:id` | state badge, registration badge, claim fields, editable when DRAFT; **actions** from `available_actions` with a form per declared field; alerts with an acknowledge form; retry when FAILED; history table | POST transition with the rendered version; PATCH draft; POST retry, acknowledge |

Registration badge states: not submitted, pending, in flight, done
(with the ID), failed (with retry), halted. While pending or in flight
the detail polls every 3 seconds.

## The three responses the UI must handle well

- **409 conflict.** A banner: "Rita approved this claim 40 seconds ago.
  Reload to see the current state." Built from `current_state` and
  `last_event`. The actions panel disables until the reload.
- **400 rule failure.** Field errors inline on the action form, from
  `errors`. The form stays open with the input preserved.
- **Blocked action.** An available action with `blocked_reason` renders
  disabled with the reason as its label's hint. Never hidden, so the
  reviewer knows the action exists and why it is unavailable.

Plus the ordinary three: loading (skeleton text, no spinner), empty
("no claims match"), and network error (retry button).

## Components

```
api/client.ts        fetch wrapper: credentials, CSRF header, JSON,
                     typed errors {status, body}
api/types.ts         Claim, ClaimEvent, AvailableAction, Registration
composables/session  me(), login(), logout(), current user
views/Login, ClaimList, ClaimDetail
components/StateBadge, RegistrationBadge, ActionPanel, ActionForm,
           ConflictBanner, HistoryTable, AlertPanel, DraftForm
```

`ActionForm` is generic: it receives `fields` from the API and renders
text, decimal, or choice inputs. Adding a transition on the server needs
no frontend change.

## Cuts

- [x] **3.1 Scaffold.** Vite + Vue + TS project, proxy, compose service,
      a page that calls `/api/health/`. `docker compose up` serves it.
- [x] **3.2 Session.** Client wrapper with CSRF, login view, router
      guard, logout. Redirect to login on 403.
- [x] **3.3 List.** Filters, empty and loading states, draft creation.
- [x] **3.4 Detail, read side.** Badges, fields, history table with
      severity highlighting and system events shown with actor "system".
- [x] **3.5 Detail, write side.** Action panel and forms from
      `available_actions`; transition call; conflict banner; inline rule
      errors; blocked actions disabled with reason; draft edit.
- [x] **3.6 Alerts and registration.** Acknowledge form with note,
      retry button, polling while pending, open-alert filter on the list.
- [x] **3.7 Close.** Vitest for `client.ts` error mapping and
      `ActionForm` rendering from a field schema; browser receipts with
      screenshots of the conflict banner, a blocked action, a rule error,
      the registration badge cycling, and an acknowledgement; NOTES.md
      stage 3; spec closure; README run instructions.

## Done when

- `docker compose up` on a clean checkout, then http://localhost:5173:
  log in as `sam`, create and submit a claim, watch the badge go pending
  then done; log in as `rita` in another window, start review, approve.
- Two reviewer windows on one claim: the second action shows the
  conflict banner naming who did what.
- A draft with no payer shows "Submit" disabled with the reason.
- An approve above the billed amount shows the error inline and keeps
  the form open.
- The seeded failed claim shows a retry; after it, the badge reaches
  done; the alert is acknowledged with a note and the flag clears.
- No lifecycle or role rule exists in the frontend source. A grep for
  state names outside the badge component finds nothing.

## Tests (D12)

Small on purpose: the server owns the rules and has 193 tests. Vitest
covers the two pieces of frontend logic that could silently break the
contract: error mapping (409 and 400 bodies to typed errors) and
field-schema rendering. Everything else is proved by the receipts.
