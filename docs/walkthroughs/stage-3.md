# Stage 3 walkthrough: frontend

Four files carry the design. Read them in this order.

## 1. The client: `frontend/src/api/client.ts`

One `request` function and three error classes. A 409 becomes
`ConflictError` carrying the server's body (current state, current
version, last event). A 400 becomes `ValidationError` with `errors` as
a flat `{field: message}` map, whether the server sent the unified
shape or DRF's default `{field: [messages]}`. Everything else is
`ApiError` with the status and the server's `detail` as the message.
The CSRF token is read from the cookie and sent on every non-GET;
credentials are same-origin because the Vite dev server proxies
`/api` to the API container. That is why CORS never comes up and the
session stays first-party.

## 2. The action panel: `ActionPanel.vue` and `ActionForm.vue`

Buttons come from `available_actions` and nothing else. A blocked
action renders disabled with its reason visible, never hidden.
`ActionForm` is generic: it renders a textarea, a decimal input, or a
select from the field schema the API declares for the action. Adding a
transition on the server needs no frontend change, and there is a
component test for each field type.

## 3. The detail view: `ClaimDetailView.vue`

The transition call sends the version the page rendered. On success
the response replaces the claim, so the next action carries the new
version and the new action list. On a rule failure the version is
untouched and the form stays open with its input. On a conflict the
banner is built from the 409 body ("rob approved this 11 seconds ago;
it is now approved") and the whole panel, including any open form,
freezes until reload. The draft edit form appears only when the API
says `can_edit`. While a registration is pending or in flight the
view polls every three seconds and stops when it settles.

## 4. The alerts: `AlertPanel.vue`

The panel renders the detail payload's `alerts` list: each alert
carries its acknowledgement, if any, and whether the caller may
acknowledge it. The client derives nothing from history and checks no
role. Acknowledging requires a note; the server enforces it and the
panel shows the server's message. The retry button likewise appears
only when the registration block says `can_retry`. A successful retry
leaves the alert open on purpose until a reviewer answers it.

## The proof of requirement 2

```
grep -rnE "DRAFT|SUBMITTED|UNDER_REVIEW|INFO_REQUESTED|APPROVED|DENIED|WITHDRAWN|submitter|reviewer" frontend/src
```

returns nothing. State labels and denial reasons come from
`GET /api/meta/`; whether the user may create claims comes from the
user payload; whether a claim may be edited, which alerts are open and
who may acknowledge them, and whether a registration may be retried
all come from the detail. The frontend decides nothing.

## What review caught before the interview would have

- The login hint named the roles in a string literal, which the grep
  above would have flagged.
- A network failure during the session check left a blank page.
- Two quick filter changes could race and show the older result.
- A failure on a fieldless action such as Submit had no visible
  surface at all.
- An open form stayed live during a conflict, and the edit form could
  outlive the draft state.
- A background poll could overwrite a fresh action with an older
  response and manufacture a false conflict.
- The alert panel re-derived a server rule from an action name, and
  submitters were offered an acknowledge form the server always
  refused. Both fixed the same way as `can_edit`: the API says so.
- An expired session on a write showed an inline error with no way
  back to login; unauthenticated requests are now 401.

## Likely live-session extensions

- **Add a transition on the server.** Zero frontend changes: the
  button, the form, and the blocked reason all come from the API.
- **Add a role.** The frontend reads capability flags, not roles, so
  the change is to what the API puts in `can_create_claims`,
  `can_edit`, `can_acknowledge`, `can_retry`, and `available_actions`.
- **Real-time instead of polling.** The polling lives in one `watch`
  in the detail view; a server-sent events stream would replace that
  one function.
