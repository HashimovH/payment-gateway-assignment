# Payment Gateway API

A payment gateway API that lets merchants process card payments through a simulated acquiring bank.

## How to run

Only Docker and `make` are needed: every command runs inside a container.

```bash
make run
make migrate
make create-merchant NAME="Acme Shop"
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

`make test`, `make test-unit`, `make test-integration`, `make lint`, `make format`, `make coverage`.
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
- **lint** runs `ruff check` and `ruff format --check`.
- **unit-tests** and **integration-tests** run with coverage and upload JUnit and coverage
  reports. Integration tests start the test database and bank simulator with `docker compose`,
  the same services as `make test-db-up`.
- **build-image** builds the production image from `prod.Dockerfile` once all checks pass.

The image is built but not yet pushed or deployed. The next step is to push it to a registry, run the helm upgrade and use `initcontainers` for migrations there.

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
being lost. A background reconciliation job would then check those records against the bank.

## Future plans

1. Background job setup, including the reconciliation job for `Pending` payments.
2. Kubernetes Helm charts for the API, cron jobs, and an init container that runs migrations.
3. A readiness check that queries the database, and configurable connection pool sizes.
4. Metrics and tracing with Prometheus and Grafana, starting with the four golden signals
   (latency, traffic, errors, saturation).
5. Dependency injection with [Dishka](https://github.com/reagento/dishka) in place of the
   hand-written FastAPI dependencies, with explicit app, request and session scopes.
6. A central router setup as the number of routers grows: one versioned API router (e.g. `/v1`)
   that includes the feature routers, so `app.py` only mounts a single router.
7. Asynchronous payment processing. The bank call currently happens inside the request. The plan
   is a transactional outbox: payments are processed and their status checked asynchronously,
   with retries where needed, and merchants are notified of status changes through webhooks.
8. Rate limiting per merchant, starting with `POST /payments`.
9. `CLAUDE.md` and `AGENTS.md` files that describe the project's conventions and workflows for
   AI coding agents.
10. A status page for bank outages. When the acquiring bank is down, we can tell merchants about
    it there and switch off payments to that bank with one change. New payments then fail fast
    with a clear error instead of waiting for timeouts.

## AI Usage

During the research phase I used AI to discuss the base setup and to learn how the payment gateway domain works. The tests were generated with AI. Throughout development I used AI as an
assistant rather than delegating everything to it, so that I could ensure the code quality myself.