COMPOSE := docker compose
API := $(COMPOSE) run --rm --no-deps api
API_WITH_DEPS := $(COMPOSE) run --rm api

.PHONY: build
build:
	@$(COMPOSE) build api

.PHONY: run
run:
	@$(COMPOSE) up -d --build

.PHONY: stop
stop:
	@$(COMPOSE) --profile test down

.PHONY: logs
logs:
	@$(COMPOSE) logs -f api

.PHONY: test
test: test-db-up
	@$(API) python -m pytest -vv --cov --cov-report=term-missing

.PHONY: test-unit
test-unit:
	@$(API) python -m pytest tests/unit --cov --cov-report=term-missing

.PHONY: test-integration
test-integration: test-db-up
	@$(API) python -m pytest tests/integration -vv --cov --cov-report=term-missing

.PHONY: test-db-up
test-db-up:
	@$(COMPOSE) up -d --wait test_db bank_simulator

# Data lives in tmpfs, so removing the container wipes it.
.PHONY: test-db-down
test-db-down:
	@$(COMPOSE) rm --stop --force test_db

.PHONY: lint
lint:
	@$(API) sh -c "ruff check . && ruff format --check . && mypy"

.PHONY: typecheck
typecheck:
	@$(API) mypy

.PHONY: format
format:
	@$(API) sh -c "ruff check . --fix && ruff format ."

.PHONY: migrate
migrate:
	@$(API_WITH_DEPS) alembic upgrade head

# make migrate-down            -> one step back (-1)
# make migrate-down level=-2   -> two steps back
# make migrate-down level=base -> revert all migrations
# make migrate-down level=<revision_id> -> down to a specific revision
level ?= -1
.PHONY: migrate-down
migrate-down:
	@$(API_WITH_DEPS) alembic downgrade $(level)

# make migration name="create payments table"
.PHONY: migration
migration:
ifndef name
	$(error name is required, e.g. make migration name="create payments table")
endif
	@$(API_WITH_DEPS) alembic revision --autogenerate -m "$(name)"

# make create-merchant NAME="Acme Shop"
.PHONY: create-merchant
create-merchant:
	@$(API_WITH_DEPS) python -m payment_gateway_api.cli create-merchant "$(NAME)"

.PHONY: coverage
coverage: test-db-up
	@$(API) python -m pytest --cov --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
