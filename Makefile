.PHONY: install
install:
	@poetry install

.PHONY: run
run:
	@poetry run python main.py

.PHONY: test
test:
	@poetry run python -m pytest -vv --cov --cov-report=term-missing

.PHONY: test-unit
test-unit:
	@poetry run python -m pytest tests/unit --cov --cov-report=term-missing

.PHONY: lint
lint:
	@poetry run ruff check .
	@poetry run ruff format --check .

.PHONY: format
format:
	@poetry run ruff check . --fix
	@poetry run ruff format .

.PHONY: migrate
migrate:
	@poetry run alembic upgrade head

# make migrate-down            -> one step back (-1)
# make migrate-down level=-2   -> two steps back
# make migrate-down level=base -> revert all migrations
# make migrate-down level=<revision_id> -> down to a specific revision
level ?= -1
.PHONY: migrate-down
migrate-down:
	@poetry run alembic downgrade $(level)

# make migration name="create payments table"
.PHONY: migration
migration:
ifndef name
	$(error name is required, e.g. make migration name="create payments table")
endif
	@poetry run alembic revision --autogenerate -m "$(name)"

# make create-merchant NAME="Acme Shop"
.PHONY: create-merchant
create-merchant:
	@poetry run python -m payment_gateway_api.cli create-merchant "$(NAME)"

.PHONY: coverage
coverage:
	@poetry run python -m pytest --cov --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
