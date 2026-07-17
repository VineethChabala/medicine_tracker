import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models.models import Base  # noqa: F401 — ensures all models are registered
from app.routers import auth, medications, patients, ocr, webhook
from app.services.scheduler import create_scheduler
from app.services.telegram_service import set_webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

import asyncio
import httpx
from app.database import AsyncSessionLocal
from app.routers.webhook import process_telegram_update

async def telegram_polling_runner():
    """Polls Telegram for updates when webhook_url is not configured (local dev fallback)."""
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Polling runner skipped.")
        return

    logger.info("Starting Telegram Bot long-polling runner (local dev mode)...")
    offset = 0
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                resp = await client.get(url, params={"offset": offset, "timeout": 20})
                if resp.status_code == 200:
                    updates = resp.json().get("result", [])
                    for update in updates:
                        async with AsyncSessionLocal() as db:
                            try:
                                await process_telegram_update(update, db)
                            except Exception as e:
                                logger.error(f"Error processing update: {e}")
                        offset = update["update_id"] + 1
                else:
                    logger.error(f"Telegram getUpdates status {resp.status_code}: {resp.text}")
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info("Telegram polling runner task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in Telegram polling runner: {e}")
                await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# Lifespan context — runs on startup and shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting Medicine Refill Tracker API...")

    # Create DB tables (Alembic handles production migrations; this is for dev convenience)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified.")

    # Start APScheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started — daily refill check at 08:00 AM IST (02:30 UTC)")

    # Start polling or set webhook
    polling_task = None
    if settings.webhook_url and settings.telegram_bot_token:
        full_webhook_url = f"{settings.webhook_url.strip().rstrip('/')}/api/webhook/"
        logger.info(f"Registering Telegram webhook: {full_webhook_url}")
        ok = await set_webhook(full_webhook_url)
        if ok:
            logger.info(f"Telegram webhook registered successfully: {full_webhook_url}")
        else:
            logger.warning(f"Failed to set Telegram webhook — URL tried: {full_webhook_url}")
    elif settings.telegram_bot_token:
        polling_task = asyncio.create_task(telegram_polling_runner())

    yield  # Hand off to the application

    # ── Shutdown ─────────────────────────────────────────────────────────
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    scheduler.shutdown()
    logger.info("Scheduler stopped. Shutting down.")



# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    application = FastAPI(
        title="Medicine Refill Tracker",
        description=(
            "Caregiver-facing API for tracking medications, calculating refill deadlines, "
            "sending Telegram alerts, and checking drug interactions."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow the Next.js frontend to communicate
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://*.vercel.app",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers under /api prefix
    application.include_router(auth.router, prefix="/api")
    application.include_router(patients.router, prefix="/api")
    application.include_router(medications.router, prefix="/api")
    application.include_router(ocr.router, prefix="/api")
    application.include_router(webhook.router, prefix="/api")

    @application.get("/health", tags=["System"])
    async def health_check():
        return {"status": "ok", "service": "medicine-refill-tracker"}

    return application


app = create_app()
