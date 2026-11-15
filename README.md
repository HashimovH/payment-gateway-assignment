# Payment Gateway API

A payment gateway API that lets merchants process card payments through a simulated acquiring bank.

## How to run

```bash
docker compose up -d --build            # API, Postgres and bank simulator
make migrate                            # apply DB migrations
make create-merchant NAME="Acme Shop"   # prints the merchant API key (shown once)
```

Open `http://localhost:8000/docs` and authorize with the merchant API key. Requests are
authenticated with `Authorization: Bearer <api-key>`, and `POST /payments` also requires an
`Idempotency-Key` header.

### Production

```bash
make run-prod WORKERS=4                                    # locally, production settings
docker build -f prod.Dockerfile -t payment-gateway-api .   # production image
```

In production mode the API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled and logs are JSON.

### Quality

`make test`, `make test-unit`, `make test-integration`, `make lint`, `make format`, `make coverage`.

## Design decisions

A payment request goes through these steps:

1. **Validation**: card number, expiry, currency, amount and CVV are checked first; invalid
   requests never reach the database.
2. **Pending record**: the payment is saved as `Pending` together with its `Idempotency-Key`, so a
   retried request can't charge the card twice.
3. **Bank call**: the request is sent to the acquiring bank, and the record is updated to
   `Authorized` or `Declined`.

If the bank call succeeds but the final update fails, the payment stays `Pending` instead of being
lost. A background reconciliation job would then check those records against the bank.

## Future plans

1. Background job setup, including the reconciliation job for `Pending` payments.
2. Kubernetes Helm charts for the API, cron jobs, and an init container that runs migrations.
3. A readiness check that queries the database, and configurable connection pool sizes.
4. Metrics and tracing.
