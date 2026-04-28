# RuggyLab OS

Base project structure for a laboratory application built with FastAPI.

## Included

- FastAPI app scaffold
- Global app settings with `APP_NAME = "RuggyLab OS"`
- `X-Powered-By: RuggyLab-OS` response header on all API responses
- SQLAlchemy database setup
- Initial laboratory domain models and API endpoints
- JWT authentication and role-based access scaffolding
- PostgreSQL and pgAdmin `docker-compose.yml`
- `assets/` folder for logos and icons
- Initial SQL schema for the laboratory domain

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Use strong values for `SECRET_KEY` and `FIRST_SUPERUSER_PASSWORD` before starting the app outside tests. RuggyLab OS now refuses to boot with weak default security settings in non-test environments.

## Database migrations

```bash
alembic upgrade head
```

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
```

## Tests

```bash
pytest
```

API tests use a dedicated SQLite database via `TestClient` and do not start the DH36 listener.

API docs:

- http://127.0.0.1:8000/docs
