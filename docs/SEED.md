# Seed data and a live walkthrough

`docker compose up` seeds once, through the service layer, so every claim has a real history. Password for everyone is `password`.

## People

| User | Role | What they can do |
|---|---|---|
| sam | submitter | Create and edit drafts, submit, answer info requests, withdraw. Sees only their own claims. |
| rita | reviewer | Start review, request info, approve, deny, retry or reconcile a registration, acknowledge alerts. Sees every claim. |
| rob | reviewer | Same as rita. Exists so two reviewers can collide. |
| admin | superuser | Read-only admin at `/admin/`. Cannot create, change, or delete anything. |

## Claims

All ten belong to sam. References are random per database, so find them by payer and amount.

| Payer | Service | Billed | State | Registration | Why it is here |
|---|---|---|---|---|---|
| Acme Health | Aug 1 | 250.00 | Draft | none | Editable, complete, ready to submit. |
| Blue Ridge Mutual | Aug 2 | 1,200.00 | Draft | none | A second draft to withdraw. |
| Acme Health | Aug 3 | 300.00 | Submitted | worker-registered at first boot | Shows the outbox doing real work. |
| Blue Ridge Mutual | Aug 4 | 450.00 | Submitted | done, `CH-SEED0001` | Ready for a reviewer to start. |
| Cascade Care | Aug 5 | 900.00 | Under review | done | Ready to approve, deny, or request info. |
| Acme Health | Aug 6 | 175.00 | Info requested | done | rob asked for the operative report; sam must answer. |
| Cascade Care | Aug 7 | 2,000.00 | Approved | done | Final. Approved for 1,800.00 by rita. |
| Blue Ridge Mutual | Aug 8 | 640.00 | Denied | done | Final. Out of network, by rob. |
| Acme Health | Aug 9 | 80.00 | Withdrawn | none | Final. Never submitted. |
| Cascade Care | Aug 10 | 510.00 | Submitted | failed after 5 attempts | Open alert. Retry and acknowledge live here. |

## Walkthrough, about ten minutes

Use two browser profiles, or one normal and one private window, one per person. Two windows in the same profile share a session cookie, so signing in as rob in one silently makes the other rob too. Keep the worker log visible in a terminal: `docker compose logs -f worker`.

**1. sam, submitter.** Sign in. The strip shows a count per state and doubles as the filter. Open the 250.00 Acme draft. Point out the Actions panel: Submit and Withdraw are the only buttons, and the server chose them. Edit the payer, save, and show the `edit` event in history with the changed field. Submit. The state flips, Clearinghouse shows Pending then In flight, and the worker log prints the attempt. Within seconds it is Done with a submission id. Open the 175.00 Info requested claim, read rob's note, click Provide info, answer it.

**2. rita, reviewer, second window.** Sign in. The list is every claim. Open the 900.00 Cascade claim under review. Try Approve with 950.00: the rule error names the field. Approve 900.00. Open the 510.00 Cascade claim with the alert. Show the failed registration, five attempts, the alert panel. Click Retry registration and watch the worker take it. Acknowledge the alert with a note; the note is now an event and the alert badge leaves the list.

**3. The race.** Both windows on the 450.00 Blue Ridge claim, rita in one and rob in the other. rita clicks Start review. rob, still looking at the old page, clicks Start review too. rob gets the banner: changed by rita, seconds ago, reload. One writer won; the other was told exactly what happened. After the reload both may open Request info; the banner guards the write, not the form, and only one submit will land.

**4. What the server refuses.** From sam's window, paste a reviewer-only action into the API and get 403; the frontend never had the button to begin with. From the admin, open Claim events and filter by severity to show the audit trail, and note there is no add or change button anywhere.

**5. The clearinghouse, if asked.** Every call is billed and there is no idempotency key. So the worker looks up the reference before it ever registers, a timeout becomes Needs reconciliation rather than a retry, and a reviewer resolves it with a lookup-only check. To force it live, set `CLEARINGHOUSE_CALL_TIMEOUT_SECONDS: "0.1"` on the worker in `compose.yaml`, restart the worker, and submit a draft.
