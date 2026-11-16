# Payment Gateway API

A payment gateway API that lets merchants process card payments through a simulated acquiring bank.

## How to run

Only Docker and `make` are needed: every command runs inside a container.

```bash
make run
make migrate
make create-merchant NAME="HashTech Shop"
```

Open `http://localhost:8000/docs` and authorize with the merchant API key. Requests are
authenticated with `Authorization: Bearer <api-key>`, and `POST /payments` also requires an
`Idempotency-Key` header.

### Production

```bash
docker build -f prod.Dockerfile -t payment-gateway-api .
```

In production mode the API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled and logs are JSON.

### Quality

`make test`, `make test-unit`, `make test-integration`, `make lint` (ruff and mypy), `make typecheck`,
`make format`, `make coverage`.
`make stop` stops all containers.

### CI/CD

GitHub Actions ([ci.yml](.github/workflows/ci.yml)) runs on pushes to `master` and on pull requests:

```
python-setup ──┬── lint ──────────────┐
               ├── unit-tests ────────┼── build-image
               └── integration-tests ─┘
```

- **python-setup** checks that `poetry.lock` matches `pyproject.toml`, installs the dependencies
  once and caches the virtualenv. The other jobs reuse it through
  [python-job](.github/actions/python-job/action.yml), so Poetry runs only in this job.
- **lint** runs `ruff check`, `ruff format --check` and `mypy` (strict for the application code;
  tests are checked too, without requiring annotations).
- **unit-tests** and **integration-tests** run with coverage and upload JUnit and coverage
  reports. Integration tests start the test database and bank simulator with `docker compose`,
  the same services as `make test-db-up`.
- **build-image** builds the production image from `prod.Dockerfile` once all checks pass.

The image is built but not yet pushed or deployed. The next step is to push it to a registry, run the helm upgrade and use `initcontainers` for migrations there.

## Try it

The bank simulator decides the outcome by the card number's last digit:

| Card number        | Outcome                        | Response                 |
|--------------------|--------------------------------|--------------------------|
| `2222405343248877` | ends in an odd digit           | `201`, `Authorized`      |
| `2222405343248112` | ends in 2, 4, 6 or 8           | `201`, `Declined`        |
| `2222405343248870` | ends in 0: bank unavailable    | `503`, `bank_unavailable`|

```bash
curl -s http://localhost:8000/payments \
  -H "Authorization: Bearer $API_KEY" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"card_number": "2222405343248877", "expiry_month": 4, "expiry_year": 2030,
       "currency": "GBP", "amount": 1050, "cvv": "123"}'

curl -s http://localhost:8000/payments/$PAYMENT_ID -H "Authorization: Bearer $API_KEY"
```

Send the same request twice with the same `Idempotency-Key` to get the original payment back;
change the amount with the same key to get `422`.

## Design decisions

A payment request goes through these steps:

1. **Validation**: card number, expiry, currency, amount and CVV are checked first; invalid
   requests never reach the database or the bank. The spec's `Rejected` outcome is a
   `400 validation_error` response listing the invalid fields, not a stored payment: nothing was
   attempted, so there is no payment to retrieve later.
2. **Pending record**: the payment is saved as `Pending` together with its `Idempotency-Key`, so a
   retried request can't charge the card twice.
3. **Bank call**: the request is sent to the acquiring bank, and the record is updated to
   `Authorized` or `Declined`.

Bank failures are split by whether the bank may have processed the payment:

- **Not processed** (connection refused, `503`, `4xx`): the `Pending` record is deleted, so the
  merchant can safely retry with the same `Idempotency-Key`.
- **Outcome unknown** (timeout after the request was sent, other `5xx`, unreadable response): the
  payment stays `Pending` and is returned with `202 Accepted` and a `Location` header. Releasing
  it would let a retry charge the card twice. Retries with the same key return the same `Pending`
  payment (`202`) without calling the bank again, and `GET /payments/{id}` shows its status.

If the bank call succeeds but the final update fails, the payment also stays `Pending` instead of
being lost. The same happens if deleting the `Pending` record fails after a "not processed" bank
error: the request returns `202` rather than telling the merchant to retry with a key that is
still taken.

**Payments left `Pending`** stay `Pending` until a reconciliation job settles them (see Future
plans). The simulator has no endpoint to look up a payment, so such a job could not confirm what
the bank did. The payment id is already sent to the bank as the `Idempotency-Key`, so a real
bank's lookup can find it by that reference.

## Future plans

In priority order:

1. **Reconciliation job** for `Pending` payments: look each one up at the bank by its payment id,
   record the outcome with the same id and settle the transaction result.
2. **Metrics and alerts**: payments by final status, bank latency by outcome class, and the age of
   the oldest `Pending` payment, which shows stuck payments before merchants report them.
3. **Readiness check** that queries the database, separate bank connection and read timeouts, and
   configurable connection pool sizes, so a bank or database outage fails fast.
4. **Rate limiting per merchant**, starting with `POST /payments`, so one merchant can't exhaust
   the connection pool or the bank's limits for everyone.
5. **A switch for bank outages**: turn payments to a bank off with one change and publish it on a
   status page, so new payments fail fast with a clear error instead of waiting for timeouts.
6. **Asynchronous processing** with a transactional outbox and merchant webhooks, including notification logic for updates on transaction status.

## AI Usage

During the research phase, I used AI to discuss the base setup and to learn how the payment gateway
domain works. The tests were generated with AI. I also used AI to review the finished submission
and to help implement the follow-up fixes, which I reviewed and merged as separate pull requests.
Throughout development, I used AI as an assistant rather than delegating everything to it, so that
I could ensure the code quality myself.
For long-term development of the API, I would include CLAUDE.md and AGENTS.md to put our conventions
to make sure the code quality and guardrails for the project. Adding multiple skills such as 
`code-reviewer`, `qa`, and so on would be useful for agentic workflows. Last but not least,
Spec-driven development can be adopted for agentic development. 
