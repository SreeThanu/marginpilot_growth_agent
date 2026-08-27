# Razorpay scope — what executes live, and what is simulated

Stated plainly here rather than left to be discovered. Razorpay test mode is the
**financial actuator** for this project, not the project.

## The honest shape of it

Each generated world holds **12,000–28,000 customers**, and an experiment's
horizon is typically **2,000–5,700 customers per arm**. Executing every treated
order through a payments sandbox is not possible, and claiming otherwise would
be a straightforward misrepresentation.

So the split is:

| | What happens | Scale |
|---|---|---|
| **Executed live** | Order created → payment captured → webhook received → attribution recorded, through the Razorpay test API | **5 treated orders per experiment**, by default |
| **Simulated** | Outcome drawn from the world's potential outcomes `Y(0)`/`Y(1)`; contribution computed by `src/economics/` | Every remaining treated order |

The executed subset exists to demonstrate that **the full financial loop
closes** — that this is a system which can actually move money and reconcile
what it moved, not a simulation wearing a payments label. It does not carry the
evaluation, and no result in the README depends on it.

## Recorded per experiment

Every experiment writes a `PAYMENT` entry to the append-only audit trail
(`src/audit/log.py`) recording:

- `client_mode` — `razorpay_test` or `mock`
- `executed_live` — how many orders went through the API
- `simulated` — how many did not
- `order_ids` and `payment_ids` for the live subset

So for any figure in the results, a reviewer can check whether money moved and
how much of the number rests on it. `make audit EXPERIMENT=<id>` prints it.

## What "executed live" means, precisely

Under the real client, these are genuine HTTP calls to Razorpay test endpoints:

- **order creation** (`orders.create`)
- **payment link generation** (`payment_link.create`)
- **order state fetch** during reconciliation (`orders.fetch`)

**Receiving a webhook is different.** Razorpay delivers `payment.captured` to a
publicly reachable URL, which a local build does not have. So the capture event
is replayed into the receiver locally, through the identical code path a real
delivery would take — same signature verification, same idempotency key, same
attribution write. Nothing about the receiver is stubbed; only the transport is.

The audit trail records this separately from `client_mode`:

| field | meaning |
|---|---|
| `client_mode` | `razorpay_test` if orders were created against the API, `mock` otherwise |
| `webhook_source` | how the capture event reached the receiver |

Stating it this way means "this ran against Razorpay" can never be read as more
than it is. To close the last gap, the webhook endpoint needs a public tunnel
and the Razorpay dashboard pointed at it — worth doing for the demo, and not
something a reader should have to infer.

## Credentials, and what this build actually ran on

`src/payments/razorpay_client.py` provides two implementations of one Protocol:

- `RazorpayTestClient` — the real SDK, **test mode only**.
- `MockRazorpayClient` — identical interface, deterministic ids, no network.

**No Razorpay test credentials were available in this build environment, so
everything here ran against `MockRazorpayClient`.** The interface, the webhook
path, the idempotency key and the reconciliation logic are all exercised; the
network call is not. `default_client()` selects the real client automatically
when `RAZORPAY_TEST_KEY_ID` and `RAZORPAY_TEST_KEY_SECRET` are present, and the
audit trail records which one was used, so a later run with credentials is
distinguishable from this one in the data rather than only in the prose.

## Live keys are refused

`RazorpayTestClient` raises `LiveKeyRefused` at construction on any key that
does not carry the `rzp_test_` prefix, and names `rzp_live_` explicitly. CLAUDE.md
requires test mode only; a guard is cheap, and discovering that a student
project charged a real card is not.

## What is deliberately absent

No refunds, no settlements, no retries beyond webhook reconciliation, no
subscription handling, no payment-method routing. Those are a payments product.
This is an actuator, and it is small on purpose.
