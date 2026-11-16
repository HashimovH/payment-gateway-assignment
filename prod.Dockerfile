FROM python:3.15-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.4 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root


FROM deps AS production

RUN pip uninstall -y poetry

COPY alembic.ini ./
COPY migrations ./migrations
COPY payment_gateway_api ./payment_gateway_api

RUN useradd --system --no-create-home app
USER app

EXPOSE 8000

ENV ENVIRONMENT=production \
    WORKERS=4

CMD ["sh", "-c", "exec uvicorn payment_gateway_api.app:app --host 0.0.0.0 --port 8000 --workers ${WORKERS} --proxy-headers --no-server-header"]
