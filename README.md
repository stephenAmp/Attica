# Attica

An AI interaction data plane. This scaffold prepares the API and database;
the Week 1 ingestion features are yours to implement.

## Start locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Docker
Desktop, and start Docker Desktop. Run these commands from the repository root:

```sh
cp .env.example .env
uv sync --locked
docker compose up -d --wait postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --no-access-log
```

Open [Swagger UI](http://127.0.0.1:8000/docs).
`GET /health/live` checks the API. `GET /health/ready` checks PostgreSQL and returns
503 when it cannot connect. Readiness does not verify the migration version.

Python 3.12 is pinned in `.python-version`; uv installs it if needed.
Dependencies are locked in `uv.lock`. `.env` is ignored by Git.
The development database is `attica`, with user `attica` and password
`attica_local`. PostgreSQL is exposed only on localhost, port 5433.
If that port is occupied, change both `POSTGRES_PORT` and `DATABASE_URL` in `.env`.
These credentials are only for local development.

## Project layout

```text
app/
  main.py              FastAPI application and engine lifecycle
  api/health.py        Liveness and database readiness endpoints
  core/config.py       Environment settings
  storage/postgres.py  SQLAlchemy Base and per-request session dependency
  models/              Import your ORM models here for Alembic discovery
migrations/            Async Alembic environment and revision template
tests/                 Health endpoint tests
compose.yaml           Local PostgreSQL with persistent storage
```

## Database usage and migrations

The API uses SQLAlchemy 2 async sessions and asyncpg. Database waits yield to
other requests, which suits concurrent ingestion. This does not replace the
durable processing workers planned for later weeks. Each request gets its own
session; never share it between concurrent tasks.

Inject `Annotated[AsyncSession, Depends(get_session)]` into endpoints, importing
`get_session` from `app.storage.postgres`. Write handlers must explicitly
`await session.commit()` or use `async with session.begin():`. Session cleanup
rolls back uncommitted work. Commit before returning a successful write response.

After adding an ORM model inheriting from `Base`, import it in
`app/models/__init__.py`, then run:

```sh
uv run alembic revision --autogenerate -m "create interactions"
# Review the generated upgrade and downgrade before applying them.
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

There are intentionally no application tables or baseline revision yet.
`upgrade head` initializes Alembic's version table; your first model produces
the first revision. Tables are managed by Alembic, never created on API startup.
Autogeneration cannot infer every change (especially renames), so review the SQL.

## Checks and database tools

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker compose exec postgres psql -U attica -d attica
docker compose logs -f postgres
docker compose stop
```

The automated health tests use a mocked database session and need no running
PostgreSQL. Verify the real connection with `/health/ready` after starting the API.
The named Docker volume preserves data across container restarts and
`docker compose down`. Removing that volume deletes the data. Changing database
credentials in `.env` does not change users in an already initialized volume.

## Your Week 1 work

1. Define Pydantic request and response schemas, including a schema version,
   event ID, event time, ingestion time, model, usage, latency, and status.
2. Design tenant authentication. Derive tenant identity from authenticated
   credentials; do not trust a request body's `tenant_id`.
3. Create the interaction ORM model and its first Alembic migration.
4. Implement `POST /v1/interactions` and a retrieval endpoint. Scope reads and
   writes to the authenticated tenant and commit writes before acknowledging.
5. Add tests for validation, persistence, authentication, and tenant isolation.

Week 1 is complete when events can be submitted, stored, retrieved, and safely
rejected when invalid. Kafka, ClickHouse, scoring, and workers come later.

Implementation references: [SQLAlchemy async sessions](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
and [Alembic async migrations](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).


## Kafka workers

Apply the reviewed migrations before starting workers (`uv run alembic upgrade head`).
Start Kafka and initialize the topic with `docker compose up -d kafka kafka-init`.
Run each worker in a separate terminal:

```sh
uv run python -m app.workers.publisher_main
uv run python -m app.workers.consumer_main
```

The consumer validates schema version 1 and verifies that the interaction belongs
to the event tenant. It writes one `processed_events` summary per event ID:
total tokens, latency, error status, empty-response flag, and processing time.
The summary and deduplication marker are the same row, committed together before
the Kafka offset advances. These are basic measurements, not quality scores.

Repeated delivery leaves the original summary unchanged. Processing failures stop
the consumer without committing the offset; restart it after resolving the cause.
Automatic consumer retries and a dead-letter topic are still future work. The
publisher retries failed batches; delivery remains at least once.
