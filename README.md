# RuggyLab OS

RuggyLab OS is a FastAPI-based laboratory information backend designed for clinical workflows such as patient intake, sample tracking, result validation, reagent monitoring, reporting, and device-oriented operations.

## Highlights

- JWT authentication with role-based access control
- FastAPI REST API with interactive docs
- SQLAlchemy models and Alembic migrations
- Patient, sample, equipment, result, reagent, audit, and reporting modules
- Specialized flows for imaging and POCT result ingestion
- Security hardening for non-test environments

## Project structure

- `app/api/`: API routers, dependencies, and endpoint modules
- `app/core/`: configuration, middleware, and security helpers
- `app/db/`: SQLAlchemy session and base setup
- `app/models/`: ORM models
- `app/schemas/`: request and response schemas
- `app/services/`: business logic, interfacing, validation, and audit services
- `alembic/`: database migrations
- `tests/`: automated test suite

## Quick start

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the environment

```bash
copy .env.example .env
```

Update at least these values before running outside tests:

- `SECRET_KEY`
- `FIRST_SUPERUSER_PASSWORD`
- database credentials if you are not using the local SQLite example

RuggyLab OS refuses to start in non-test environments when security settings are still weak or default-like.

### 4. Start the application

```bash
uvicorn app.main:app --reload
```

## API documentation

Once the server is running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health endpoint: `http://127.0.0.1:8000/api/v1/health`

## Database

### Run migrations

```bash
alembic upgrade head
```

### Create a new migration

```bash
alembic revision --autogenerate -m "describe change"
```

## Testing

Run the test suite with:

```bash
pytest
```

The API tests use a dedicated SQLite database through `TestClient` and do not start the DH36 listener.

## Security notes

- Sensitive CRUD routes require authentication
- Administrative actions are restricted by role checks
- Result validation fields are enforced server-side
- Imaging path generation is sanitized to avoid path traversal issues
- Local `.env` values are ignored by Git; use `.env.example` as the template

## Deployment notes

The repository includes:

- `docker-compose.yml` for PostgreSQL and pgAdmin
- Alembic for schema migration management
- a first API and domain structure suitable for extension
