# RuggyLab OS

[![Release](https://img.shields.io/github/v/release/rommellnelson-ux/ruggylab-os?display_name=tag)](https://github.com/rommellnelson-ux/ruggylab-os/releases)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-GPL--2.0-lightgrey.svg)](https://github.com/rommellnelson-ux/ruggylab-os)

RuggyLab OS is a FastAPI-based laboratory information backend designed for clinical workflows such as patient intake, sample tracking, result validation, reagent monitoring, reporting, and device-oriented operations.

> Laboratory backend for patient intake, sample lifecycle tracking, result validation, reagent control, auditability, and device-oriented workflows.

## Why RuggyLab OS

RuggyLab OS provides a backend foundation for laboratory operations where traceability, access control, and operational visibility matter. It combines clinical workflow entities with reporting, inventory-oriented monitoring, and audit events in a single FastAPI codebase.

## Repository profile

- Status: active backend foundation
- Primary focus: secure laboratory operations and traceable workflows
- Best fit: internal lab systems, prototypes, and operational backends that need auditable API flows

## Highlights

- JWT authentication with role-based access control
- FastAPI REST API with interactive docs
- SQLAlchemy models and Alembic migrations
- Patient, sample, equipment, result, reagent, audit, and reporting modules
- Specialized flows for imaging and POCT result ingestion
- Security hardening for non-test environments

## Main use cases

- Register and search patients
- Track samples from intake to processing
- Record manual or device-linked laboratory results
- Monitor reagents, consumption ratios, and stock alerts
- Review dashboards, audit events, and operational activity
- Reserve microscopy image paths and process POCT-oriented flows

## Technical snapshot

- Framework: FastAPI
- ORM: SQLAlchemy
- Migrations: Alembic
- Auth: JWT bearer tokens
- Default docs UI: Swagger
- Supported local setup: SQLite or PostgreSQL

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

## Core API areas

- `auth`: login and token issuance
- `users`: current user and admin-managed user operations
- `patients`: patient registration and search
- `samples`: sample creation and listing
- `results`: laboratory result creation and filtering
- `reagents`: stock management and audit-linked reagent actions
- `reports`: stock, audit, threshold, and monthly consumption dashboards
- `operations`: operational validation endpoints
- `imaging`: microscope capture reservation flow
- `ratio-presets` and `equipment-reagent-ratios`: reagent consumption modeling

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

## Roadmap ideas

- Frontend or admin dashboard integration
- Background jobs for device ingestion and reporting automation
- Richer validation workflows for additional analyzers
- CI pipeline for linting, tests, and release automation
