# Expense Sharing API

A production-ready REST API for splitting expenses among groups of people.
Built with modern Python async stack - FastAPI, SQLAlchemy 2.0, PostgreSQL, Celery, Redis.

## Features

- **4 split types**: equal, exact, percentage, shares
- **Debt simplification**: Greedy Min Cash Flow algorithm minimizes the number of transactions needed to settle all debts
- **Async email notifications**: Celery tasks notify members on new expenses and settlements
- **Weekly summaries**: Celery Beat sends balance reports every Monday
- **Full audit trail**: Settlements never modify expense records, balance is always recalculated in real-time

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Framework | FastAPI 0.115 | Async-native, automatic OpenAPI, Pydantic v2 integration |
| ORM | SQLAlchemy 2.0 async | Type-safe, async-native, production-proven |
| Database | PostgreSQL 16 | ACID transactions, `Numeric` type for precise monetary values |
| Migrations | Alembic | Version-controlled schema changes |
| Cache / Broker | Redis 7 | Celery broker + result backend |
| Task Queue | Celery 5 + Beat | Async email tasks, scheduled weekly summaries |
| Email | fastapi-mail | Async SMTP integration |
| Auth | PyJWT + argon2-cffi | Short-lived access tokens + argon2id password hashing (PHC winner) |
| Package Manager | uv | 10-100x faster than pip, lock file for reproducible builds |
| Containers | Docker + Compose | Reproducible dev and production environments |
| Testing | pytest-asyncio + httpx | Async integration tests with rollback isolation |

## Architecture

┌─────────────────────────────────────────────────────┐
│                    Docker Network                   │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐   │
│  │  FastAPI │    │  Celery  │    │ Celery Beat  │   │
│  │  :8000   │    │  Worker  │    │ (scheduler)  │   │
│  └────┬─────┘    └────┬─────┘    └──────┬───────┘   │
│       │               │                 │           │
│  ┌────▼───────────────▼─────────────────▼───────┐   │
│  │              Redis :6379                     │   │
│  │   DB/0: cache  DB/1: broker  DB/2: results   │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │            PostgreSQL :5432                 │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘

## Running Locally

**Prerequisites:** Docker, Docker Compose

```bash
# 1. Clone
git clone https://github.com/yourusername/expense-sharing-api
cd expense-sharing-api

# 2. Configure environment
cp .env.example .env
# Edit .env: fill in SECRET_KEY, Mailtrap credentials
# Generate SECRET_KEY:
openssl rand -hex 32

# 3. Start all services
docker compose up --build -d

# 4. Run migrations
docker compose run --rm api uv run alembic upgrade head

# 5. Open API docs
open http://localhost:8000/docs
```

## API Overview

| Group | Endpoint | Description |
|---|---|---|
| Auth | `POST /api/v1/auth/register` | Create account |
| Auth | `POST /api/v1/auth/login` | Login, receive JWT tokens |
| Auth | `POST /api/v1/auth/refresh` | Refresh access token |
| Auth | `GET /api/v1/auth/me` | Current user info |
| Groups | `POST /api/v1/groups` | Create group |
| Groups | `GET /api/v1/groups` | List my groups |
| Groups | `GET /api/v1/groups/{id}` | Group detail + members |
| Groups | `POST /api/v1/groups/{id}/members` | Invite member (admin) |
| Groups | `DELETE /api/v1/groups/{id}/members/{uid}` | Remove member (admin) |
| Groups | `DELETE /api/v1/groups/{id}/leave` | Leave group |
| Groups | `GET /api/v1/groups/{id}/balances` | Net balances + simplified debts |
| Expenses | `POST /api/v1/groups/{id}/expenses` | Add expense |
| Expenses | `GET /api/v1/groups/{id}/expenses` | List expenses (paginated) |
| Expenses | `GET /api/v1/groups/{id}/expenses/{eid}` | Expense detail |
| Expenses | `DELETE /api/v1/groups/{id}/expenses/{eid}` | Soft delete expense |
| Settlements | `POST /api/v1/groups/{id}/settlements` | Record payment |
| Settlements | `GET /api/v1/groups/{id}/settlements` | Group settlement history |
| Settlements | `GET /api/v1/groups/{id}/settlements/mine` | My settlements |

## Running Tests

```bash
# Create test database (one-time)
docker compose exec db psql -U postgres -c "CREATE DATABASE expense_sharing_test;"

# Run all tests
docker compose run --rm api uv run pytest tests/ -v
```

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `APP_ENV` | Environment (`development`/`production`) | `development` |
| `SECRET_KEY` | JWT signing key (min 32 chars) | `openssl rand -hex 32` |
| `DATABASE_URL` | PostgreSQL async URL | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | Celery broker (Redis DB 1) | `redis://redis:6379/1` |
| `CELERY_RESULT_BACKEND` | Celery results (Redis DB 2) | `redis://redis:6379/2` |
| `MAIL_SERVER` | SMTP server | `sandbox.smtp.mailtrap.io` |
| `ALLOWED_ORIGINS` | CORS origins (production) | `https://yourdomain.com` |

## Project Structure

app/
├── api/v1/                 # Route handlers (thin layer — calls services)
├── core/                   # Config, security, dependencies
├── db/
│   ├── models/             # SQLAlchemy ORM models
│   └── session.py          # Async engine and session factory
├── schemas/                # Pydantic v2 request/response schemas
├── services/               # Business logic (fat layer)
│   └── balance_service.py  # Debt algorithm lives here
└── tasks/                  # Celery tasks and email helpers
