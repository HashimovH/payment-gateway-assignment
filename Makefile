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

.PHONY: coverage
coverage:
	@poetry run python -m pytest --cov --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
