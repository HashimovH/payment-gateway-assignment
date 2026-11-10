.PHONY: install
install:
	@poetry install

.PHONY: run
run:
	@poetry run python main.py

.PHONY: test
test:
	@poetry run python -m pytest -vv --cov --cov-report=term-missing

.PHONY: coverage
coverage:
	@poetry run python -m pytest --cov --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"
