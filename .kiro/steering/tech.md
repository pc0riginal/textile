# Tech Stack

## Runtime & Framework
- Python 3.11+
- FastAPI (0.104.x) — async web framework
- Uvicorn — ASGI server (with `--reload` in dev, `--workers 4` in production)

## Database
- MongoDB (via Motor 3.3.x async driver, PyMongo 4.6.x)
- No ORM — direct collection access through `app/database.py` helper (`get_collection`)
- All queries use raw MongoDB filter dicts with `bson.ObjectId` for document IDs

## Templating & Frontend
- Jinja2 server-side templates (`app/templates/`)
- Static assets served via FastAPI `StaticFiles` (`app/static/`)
- Vanilla JavaScript (`app/static/js/`) — no frontend framework
- Custom searchable dropdown component (`searchable-dropdown.js`)

## Authentication & Security
- JWT tokens (python-jose) stored in HTTP cookies (`access_token`)
- Password hashing with bcrypt (direct, no passlib wrapper)
- Dependency injection for auth: `get_current_user`, `get_current_company`

## Key Libraries
- pydantic — request/response models and validation
- python-decouple — environment config (`config.py`)
- openpyxl — Excel export
- pillow — image handling
- aiofiles — async file I/O
- python-multipart — form data parsing

## Configuration
- Environment variables via `.env` or system env, read through `python-decouple`
- Key settings: `MONGODB_URL`, `DATABASE_NAME`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`

## Containerization
- Dockerfile (Python 3.11-slim, non-root user)
- docker-compose.yml for deployment

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (with auto-reload)
python start.py
# or directly:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Initialize database with admin user
python -c "import asyncio; from init_db import init_database; from app.database import connect_to_mongo; asyncio.run(connect_to_mongo()); asyncio.run(init_database())"

# Docker
docker-compose up --build
```
