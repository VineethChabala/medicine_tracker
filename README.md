# Medicine Refill Tracker

A caregiver-facing web application that tracks medications for patients, calculates refill deadlines, sends Telegram alerts, and checks drug interactions.

**Stack:** FastAPI + PostgreSQL (Railway) · Next.js (Vercel) · Telegram Bot · Gemini Vision · NIH RxNav

---

## Quick Start (Local Development)

### Prerequisites
- Docker Desktop installed and running
- Node.js 20+ installed
- Python 3.12+ (optional, only if running backend outside Docker)

### 1. Clone and configure environment

```bash
# Copy environment template
cp .env.example .env
# Edit .env and fill in API keys (Telegram, Gemini, etc.)
```

### 2. Start the backend (FastAPI + Postgres)

```bash
docker compose up -d
```

- API will be available at: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Postgres: localhost:5432

### 3. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

> **Note:** On first run, `main.py` auto-creates all tables via SQLAlchemy. Alembic migrations are used for production schema changes.

### 4. Start the frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000

---

## Project Structure

```
medicine-tracker/
├── docker-compose.yml          # Local dev orchestration
├── .env.example                # Environment variable template
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py
│   └── app/
│       ├── main.py             # App factory + lifespan (scheduler, webhook)
│       ├── config.py           # Pydantic settings from env
│       ├── database.py         # Async SQLAlchemy engine + session
│       ├── dependencies.py     # JWT auth dependency
│       ├── models/
│       │   └── models.py       # All ORM table definitions
│       ├── schemas/
│       │   └── schemas.py      # Pydantic request/response schemas
│       ├── routers/
│       │   ├── auth.py         # /api/auth/*
│       │   ├── patients.py     # /api/patients/*
│       │   ├── medications.py  # /api/patients/{id}/medications
│       │   ├── ocr.py          # /api/patients/{id}/prescriptions/scan
│       │   └── webhook.py      # /api/webhook (Telegram)
│       └── services/
│           ├── auth_service.py       # JWT + bcrypt
│           ├── drug_resolver.py      # 4-layer Indian drug name resolution
│           ├── interaction.py        # RxNav API + DB cache
│           ├── scheduler.py          # APScheduler daily job
│           └── telegram_service.py   # Telegram Bot API sender
│
├── frontend/
│   ├── .env.local              # NEXT_PUBLIC_API_URL
│   └── src/
│       ├── api/
│       │   └── client.ts       # Axios + JWT interceptors
│       └── app/
│           ├── login/page.tsx
│           ├── register/page.tsx
│           ├── dashboard/
│           │   ├── page.tsx                    # Patient overview
│           │   └── patients/[id]/page.tsx      # Medication detail
│           └── layout.tsx
│
└── README.md
```

---

## API Reference

All endpoints are prefixed with `/api`. See http://localhost:8000/docs for the full interactive Swagger docs.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register a new caregiver |
| `POST` | `/api/auth/login` | Login, get JWT tokens |
| `POST` | `/api/auth/refresh` | Refresh token rotation |
| `GET` | `/api/patients/` | List caregiver's patients |
| `POST` | `/api/patients/` | Add a new patient |
| `GET` | `/api/patients/{id}` | Patient details |
| `PATCH` | `/api/patients/{id}` | Update patient |
| `POST` | `/api/patients/{id}/caregivers` | Add co-caregiver by email |
| `POST` | `/api/patients/{id}/link-token` | Generate Telegram link token for patient |
| `POST` | `/api/patients/me/link-token` | Generate Telegram link token for caregiver |
| `GET` | `/api/patients/{id}/medications` | List meds with days_remaining |
| `POST` | `/api/patients/{id}/medications` | Add med (triggers resolution + interaction check) |
| `PATCH` | `/api/medications/{id}` | Update med / adjust stock |
| `DELETE` | `/api/medications/{id}` | Soft-delete medication |
| `POST` | `/api/patients/{id}/prescriptions/scan` | OCR scan prescription image |
| `POST` | `/api/patients/{id}/prescriptions/{sid}/confirm` | Confirm and bulk-add from scan |
| `POST` | `/api/webhook` | Telegram bot webhook receiver |
| `GET` | `/health` | Health check |

---

## Telegram Bot Setup

1. Message `@BotFather` on Telegram
2. Send `/newbot`, follow prompts, get `BOT_TOKEN`
3. Add `TELEGRAM_BOT_TOKEN=...` to `.env`
4. For production: set `WEBHOOK_URL=https://your-railway-app.railway.app` in env
5. The app auto-registers the webhook on startup

### Bot Commands
| Command | Description |
|---|---|
| `/start` | Welcome message + setup guide |
| `/link <token>` | Link chat to profile |
| `/status` | Show medication stock levels |
| `/refill <name> <qty>` | Add to stock |
| `/help` | Command list |

---

## Deployment

### Railway (Backend + Database)

1. Create a new Railway project
2. Add **PostgreSQL** plugin from the service catalog
3. Add a new service from your GitHub repo, pointing to `./backend` with Dockerfile build
4. Set environment variables in Railway dashboard:
   ```
   TELEGRAM_BOT_TOKEN=...
   GEMINI_API_KEY=...
   JWT_SECRET=<random 32-char hex>
   WEBHOOK_URL=https://<your-railway-subdomain>.railway.app
   ```
   > **Note:** No Google CSE key needed — Layer 3 drug search uses DuckDuckGo (free, built-in).
5. `DATABASE_URL` is automatically set by the PostgreSQL plugin

### Vercel (Frontend)

1. Connect your GitHub repo to Vercel
2. Set root directory to `frontend`
3. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-subdomain>.railway.app
   ```
4. Deploy

---

## Running Tests

```bash
# From backend directory
docker compose exec api pytest tests/ -v
```

---

## Cost Summary (Monthly)

| Service | Cost |
|---|---|
| Railway Hobby (API + Postgres) | ~$5–10/mo |
| Vercel (Next.js) | Free |
| Telegram Bot API | Free |
| Gemini API | Free tier |
| NIH RxNav API | Free |
| Google Custom Search | Free (100 queries/day) |
| **Total** | **~$5–10/mo** |
