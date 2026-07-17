"""
Telegram Bot webhook handler.
Receives updates from Telegram and dispatches commands.
"""
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CaregiverPatient, Medication, Patient, User
from app.services.auth_service import decode_token
from app.services.telegram_service import send_telegram_message

router = APIRouter(prefix="/webhook", tags=["Telegram Webhook"])
logger = logging.getLogger(__name__)


def _status_emoji(days: float) -> str:
    if days <= 3:
        return "🔴"
    if days <= 7:
        return "🟡"
    return "🟢"


async def handle_start(chat_id: int, db: AsyncSession):
    await send_telegram_message(
        chat_id,
        "💊 *Welcome to the Medicine Refill Tracker Bot!*\n\n"
        "To receive medication alerts, link this chat to your profile.\n\n"
        "1️⃣ Open the web dashboard\n"
        "2️⃣ Go to your profile or a patient's page\n"
        "3️⃣ Click *'Generate Link Token'* and copy the token\n"
        "4️⃣ Send: `/link <your-token>`\n\n"
        "Type /help for all commands.",
    )


async def handle_link(chat_id: int, token: str, db: AsyncSession):
    # Check if the token is a 6-digit code
    if token.isdigit() and len(token) == 6:
        from app.services.auth_service import verify_short_link_code
        subject = verify_short_link_code(token)
        if not subject:
            await send_telegram_message(
                chat_id,
                "❌ Invalid or expired code. Please generate a new one from the dashboard.",
            )
            return
    else:
        # Fallback to old JWT decode
        payload = decode_token(token)
        if not payload or payload.get("type") != "telegram_link":
            await send_telegram_message(
                chat_id,
                "❌ Invalid or expired token. Please generate a new one from the dashboard.",
            )
            return
        subject = payload["sub"]

    if subject.startswith("patient:"):
        patient_id = uuid.UUID(subject.split(":")[1])
        stmt = select(Patient).where(Patient.id == patient_id)
        result = await db.execute(stmt)
        patient = result.scalar_one_or_none()
        if patient:
            patient.telegram_chat_id = chat_id
            await db.commit()
            await send_telegram_message(
                chat_id,
                f"✅ Chat linked to patient profile: *{patient.full_name}*\nYou'll receive refill reminders here.",
            )
        else:
            await send_telegram_message(chat_id, "❌ Patient not found.")

    elif subject.startswith("caregiver:"):
        caregiver_id = uuid.UUID(subject.split(":")[1])
        stmt = select(User).where(User.id == caregiver_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.telegram_chat_id = chat_id
            await db.commit()
            await send_telegram_message(
                chat_id,
                f"✅ Chat linked to caregiver profile: *{user.full_name}*\nYou'll receive alerts for all your patients.",
            )
        else:
            await send_telegram_message(chat_id, "❌ Caregiver not found.")
    else:
        await send_telegram_message(chat_id, "❌ Unknown token type.")



async def handle_status(chat_id: int, db: AsyncSession):
    # Find the user/patients by chat_id
    stmt_patient = select(Patient).where(Patient.telegram_chat_id == chat_id)
    stmt_user = select(User).where(User.telegram_chat_id == chat_id)

    patient_result = await db.execute(stmt_patient)
    patients = patient_result.scalars().all()

    user_result = await db.execute(stmt_user)
    user = user_result.scalars().first()

    patients_to_show = []

    if patients:
        patients_to_show.extend(patients)
    elif user:
        # Fetch all linked patients
        cg_stmt = (
            select(Patient)
            .join(CaregiverPatient, CaregiverPatient.patient_id == Patient.id)
            .where(CaregiverPatient.caregiver_id == user.id)
        )
        cg_result = await db.execute(cg_stmt)
        patients_to_show = cg_result.scalars().all()
    else:
        await send_telegram_message(chat_id, "❌ This chat isn't linked yet. Use /link <token> to connect.")
        return

    if not patients_to_show:
        await send_telegram_message(chat_id, "No patients found. Add patients from the web dashboard.")
        return

    for p in patients_to_show:
        med_stmt = select(Medication).where(Medication.patient_id == p.id, Medication.is_active == True)
        med_result = await db.execute(med_stmt)
        meds = med_result.scalars().all()

        if not meds:
            await send_telegram_message(chat_id, f"📋 *{p.full_name}* has no active medications.")
            continue

        lines = [f"📊 *{p.full_name}'s Medication Status:*\n"]
        for med in sorted(meds, key=lambda m: m.days_remaining):
            days = med.days_remaining
            emoji = _status_emoji(days)
            lines.append(
                f"{emoji} *{med.name}* — {days:.1f} days remaining "
                f"({med.quantity_on_hand:.0f} {med.dose_unit}s left)"
            )

        await send_telegram_message(chat_id, "\n".join(lines))


async def handle_refill(chat_id: int, args: str, db: AsyncSession):
    parts = args.rsplit(maxsplit=1)
    if len(parts) != 2:
        await send_telegram_message(
            chat_id,
            "❌ *Invalid format.*\n\n"
            "**Usage:** `/refill <medication> <quantity>`\n"
            "Or: `/refill <patient>:<medication> <quantity>`\n\n"
            "Examples:\n"
            "• `/refill Ecosprin 30`\n"
            "• `/refill Grandpa:Ecosprin 30`"
        )
        return

    name_part, qty_str = parts
    try:
        qty = float(qty_str)
        if qty <= 0:
            raise ValueError()
    except ValueError:
        await send_telegram_message(chat_id, "❌ *Quantity must be a positive number.*")
        return

    # Check for patient prefix separator ':'
    patient_name_query = None
    med_name = name_part
    if ":" in name_part:
        patient_name_query, med_name = name_part.split(":", 1)
        patient_name_query = patient_name_query.strip()
        med_name = med_name.strip()

    # Find the patient/caregiver linked to this chat
    stmt_patient = select(Patient).where(Patient.telegram_chat_id == chat_id)
    patient_result = await db.execute(stmt_patient)
    patients = patient_result.scalars().all()

    patient_ids = []
    patient_map = {}

    if patients:
        for p in patients:
            patient_map[p.id] = p
        if patient_name_query:
            matching_patients = [p for p in patients if patient_name_query.lower() in p.full_name.lower()]
            if not matching_patients:
                await send_telegram_message(chat_id, f"❌ Patient matching '{patient_name_query}' not found.")
                return
            patient_ids = [p.id for p in matching_patients]
        else:
            patient_ids = [p.id for p in patients]
    else:
        stmt_user = select(User).where(User.telegram_chat_id == chat_id)
        user_result = await db.execute(stmt_user)
        user = user_result.scalars().first()
        if user:
            cg_stmt = (
                select(Patient)
                .join(CaregiverPatient, CaregiverPatient.patient_id == Patient.id)
                .where(CaregiverPatient.caregiver_id == user.id)
            )
            cg_result = await db.execute(cg_stmt)
            cg_patients = cg_result.scalars().all()
            for p in cg_patients:
                patient_map[p.id] = p
            if patient_name_query:
                matching_patients = [p for p in cg_patients if patient_name_query.lower() in p.full_name.lower()]
                if not matching_patients:
                    await send_telegram_message(chat_id, f"❌ Patient matching '{patient_name_query}' not found.")
                    return
                patient_ids = [p.id for p in matching_patients]
            else:
                patient_ids = [p.id for p in cg_patients]

    if not patient_ids:
        await send_telegram_message(chat_id, "❌ Chat not linked. Use `/link <token>` first.")
        return

    # Find the medication by name (case-insensitive)
    from sqlalchemy import func
    med_stmt = select(Medication).where(
        Medication.patient_id.in_(patient_ids),
        func.lower(Medication.name).contains(med_name.lower()),
        Medication.is_active == True,
    )
    med_result = await db.execute(med_stmt)
    matching_meds = med_result.scalars().all()

    if not matching_meds:
        await send_telegram_message(chat_id, f"❌ Medication matching '{med_name}' not found.")
        return

    if len(matching_meds) > 1:
        lines = ["⚠️ *Multiple matching medications found:*\n"]
        for m in matching_meds:
            pat = patient_map.get(m.patient_id)
            pat_name = pat.full_name if pat else "Unknown Patient"
            lines.append(f"• *{m.name}* for *{pat_name}* (use: `/refill {pat_name}:{m.name} {qty_str}`)")
        await send_telegram_message(chat_id, "\n".join(lines))
        return

    med = matching_meds[0]
    med.quantity_on_hand += qty
    await db.commit()

    new_days = med.days_remaining
    pat = patient_map.get(med.patient_id)
    pat_name = pat.full_name if pat else "Patient"
    await send_telegram_message(
        chat_id,
        f"✅ Stock updated for *{med.name}* (*{pat_name}*)!\n"
        f"📦 New quantity: {med.quantity_on_hand:.0f} {med.dose_unit}(s)\n"
        f"📅 Projected: *{new_days:.1f} days remaining*",
    )


async def handle_help(chat_id: int):
    await send_telegram_message(
        chat_id,
        "💊 *Medicine Refill Tracker — Commands*\n\n"
        "/start — Welcome message and setup guide\n"
        "/link <token> — Link this chat to your profile using a dashboard token\n"
        "/status — View current medication stock levels\n"
        "/refill <name> <qty> — Add to a medication's stock\n"
        "/help — Show this message",
    )


async def process_telegram_update(update: Dict[str, Any], db: AsyncSession):
    """Processes a single Telegram update and runs commands."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text: str = message.get("text", "").strip()

    if not chat_id or not text:
        return

    if text == "/start":
        await handle_start(chat_id, db)
    elif text.startswith("/start "):
        token = text[7:].strip()
        await handle_link(chat_id, token, db)
    elif text == "/link" or text.startswith("/link"):
        token = text[5:].strip()
        if not token:
            await send_telegram_message(
                chat_id,
                "❌ *Usage:* `/link <token>`\n"
                "Example: `/link 123456`\n\n"
                "_Generate your 6-digit code on the web dashboard._"
            )
        else:
            await handle_link(chat_id, token, db)
    elif text == "/status":
        await handle_status(chat_id, db)
    elif text == "/refill" or text.startswith("/refill"):
        args = text[7:].strip()
        if not args:
            await send_telegram_message(
                chat_id,
                "❌ *Usage:* `/refill <medication> <quantity>`\n"
                "Or: `/refill <patient>:<medication> <quantity>`\n\n"
                "Examples:\n"
                "• `/refill Ecosprin 30`\n"
                "• `/refill Grandpa:Ecosprin 30`"
            )
        else:
            await handle_refill(chat_id, args, db)
    elif text == "/help":
        await handle_help(chat_id)


@router.post("/")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receives Telegram update and dispatches the appropriate handler."""
    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    await process_telegram_update(update, db)
    return {"ok": True}

