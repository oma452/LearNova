# LearNova 🎓

AI-powered educational platform for schools: personalized learning, dynamic assessments, and actionable analytics for students, teachers, parents, and admins.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

## Features

| Role | What they get |
|------|---------------|
| **Students** | RAG chatbot over lessons (LangGraph agent + MCP), practice questions, personalized roadmaps, exams, weekly/term analytics |
| **Teachers** | PDF lesson upload (chunked + embedded into pgvector), question & exam creation, student performance tracking |
| **Parents** | Register via admin-issued access code and follow linked students |
| **Admins** | Academic terms/weeks, subjects, classrooms, role-based unique ID generation, analytics |

## Tech Stack

FastAPI · SQLAlchemy (async) · PostgreSQL + pgvector · Alembic · Redis · Celery + Flower · LangGraph / LangChain · MCP · OpenAI · Docker Compose

## Architecture

```
Router (src/Api/routers) → Controller (src/Controllers) → Service (src/Models/services) → Repository (src/Models/repositories) → DB
```

```
src/
├── Api/            # routers, schemas, dependencies, JWT utils
├── Chatbot/        # LangGraph agent (nodes, state, prompts), MCP servers, chat sessions
├── Controllers/    # orchestration between routes and services
├── Models/         # DB schemes, Alembic migrations, services, repositories
├── Stores/         # LLM + VectorDB provider abstractions (factory pattern)
├── Tasks/          # Celery tasks (email, maintenance)
├── Helpers/        # settings / config
└── utils/          # PDF processing, embeddings, file validation
Docker/             # Dockerfile, docker-compose.yml, pgvector init SQL
scripts/            # e.g. create_admin.py
```

## Quick Start

### Option A: Docker Compose (full stack)

```bash
git clone https://github.com/oma452/LearNova.git
cd LearNova
cp .env.example .env.docker      # fill in values (POSTGRES_HOST=db, REDIS_HOST=redis)
cd Docker && docker compose up -d --build
```

- API: http://localhost:8001 (docs at `/docs`)
- Flower (Celery): http://localhost:5555

### Option B: Local development

Requires Python 3.10+, PostgreSQL with pgvector, and Redis.

```bash
git clone https://github.com/oma452/LearNova.git
cd LearNova
python -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cp .env.example .env             # fill in values

cd Docker && docker compose up -d db redis && cd ..   # DB + Redis only
alembic upgrade head                                   # create tables
python scripts/create_admin.py                         # create first admin

uvicorn src.main:app --reload                          # http://localhost:8000/docs
celery -A src.celery_app worker --loglevel=info --queues=default,email_queue
```

## Authentication

JWT access/refresh tokens, email verification, and password reset.
Endpoints live under `/api/v1/auth/`: `sign-up`, `login`, `logout`, `verify-email`, `request-password-reset`, `confirm-password-reset`, `refresh_token`.

Users get human-readable role-based IDs (students `22xxx`, teachers `11xxx`, parents `P22xxx`, admins `ADMINxxx`).

## Roadmap / Known Issues

- [ ] Use Redis for the chatbot memory saver
- [ ] Add caching; move chatbot and lesson upload to background tasks
- [ ] Better file-extension/type validation
- [ ] Rework MCP server creation logic
- [ ] Add CORS and middleware
- [ ] Fix human-in-the-loop approval endpoint
- [ ] Fix student → teacher rating endpoint
- [ ] Fix `back_populates` in the `academic_term` model
- [ ] JWT expiry mismatch (handler uses 60 min, env documents 30 min)

## Contributing

1. Fork and create a branch: `git checkout -b feat/my-feature`
2. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`)
3. Open a pull request against `main`

## License

Apache License 2.0, see [LICENSE](LICENSE).
