FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    ENVIRONMENT=local

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --no-root

COPY alembic.ini main.py ./
COPY migrations ./migrations
COPY payment_gateway_api ./payment_gateway_api
COPY tests ./tests

EXPOSE 8000

CMD ["python", "main.py"]
