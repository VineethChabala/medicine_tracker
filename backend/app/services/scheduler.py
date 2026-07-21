"""
APScheduler daily refill check job.
Runs every morning at 02:30 UTC (8:00 AM IST).
"""
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import CaregiverPatient, Medication, Patient, RefillReminderLog, User
from app.services.telegram_service import send_telegram_message

logger = logging.getLogger(__name__)


def _status_emoji(days: float) -> str:
    if days <= 3:
        return "🔴"
    if days <= 7:
        return "🟡"
    return "🟢"


async def daily_refill_check():
    """Main scheduled task: calculate days remaining and send Telegram alerts."""
    logger.info("Running daily refill check...")
    async with AsyncSessionLocal() as session:
        # Fetch all active medications with their patients
        stmt = (
            select(Medication, Patient)
            .join(Patient, Medication.patient_id == Patient.id)
            .where(Medication.is_active == True)
        )
        result = await session.execute(stmt)
        rows = result.all()

        for med, patient in rows:
            # ── Auto-decrement quantity consumed today ─────────────────────────
            today = date.today()
            daily_consumption = med.frequency_per_day  # doses/day = units consumed per day
            med.quantity_on_hand = max(0.0, med.quantity_on_hand - daily_consumption)
            # Flush so days_remaining recalculates off the updated quantity
            await session.flush()

            days_left = med.days_remaining

            threshold = med.refill_threshold_days
            escalation = med.reminder_escalation_days

            if days_left > threshold:
                continue  # No alert needed

            emoji = _status_emoji(days_left)
            if days_left <= escalation:
                level = "🚨 *CRITICAL REFILL ALERT*"
            else:
                level = "⚠️ *Refill Reminder*"

            message = (
                f"{level} for *{patient.full_name}*\n\n"
                f"{emoji} *{med.name}* — {days_left:.1f} days remaining\n"
                f"📦 Stock: {med.quantity_on_hand:.0f} {med.dose_unit}(s)\n"
                f"📅 Today: {today.strftime('%d %b %Y')}\n\n"
                f"_Please refill soon to avoid missing doses._"
            )

            # Send to patient
            if patient.telegram_chat_id:
                success = await send_telegram_message(patient.telegram_chat_id, message)
                session.add(RefillReminderLog(
                    medication_id=med.id,
                    chat_id=patient.telegram_chat_id,
                    days_remaining_at_send=days_left,
                    status="sent" if success else "failed",
                ))

            # Send to all linked caregivers
            cg_stmt = (
                select(User)
                .join(CaregiverPatient, CaregiverPatient.caregiver_id == User.id)
                .where(CaregiverPatient.patient_id == patient.id)
            )
            cg_result = await session.execute(cg_stmt)
            for caregiver in cg_result.scalars().all():
                if caregiver.telegram_chat_id:
                    success = await send_telegram_message(caregiver.telegram_chat_id, message)
                    session.add(RefillReminderLog(
                        medication_id=med.id,
                        chat_id=caregiver.telegram_chat_id,
                        days_remaining_at_send=days_left,
                        status="sent" if success else "failed",
                    ))

        await session.commit()
    logger.info("Daily refill check complete.")


def create_scheduler() -> AsyncIOScheduler:
    """Creates and configures the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    # 02:30 UTC = 08:00 AM IST
    scheduler.add_job(daily_refill_check, "cron", hour=2, minute=30, id="daily_refill")
    return scheduler
