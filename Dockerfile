FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Install dependencies first so this layer is cached between code changes
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root

COPY alembic.ini ./
COPY migrations ./migrations
COPY payment_gateway_api ./payment_gateway_api

EXPOSE 8000

CMD ["uvicorn", "payment_gateway_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
