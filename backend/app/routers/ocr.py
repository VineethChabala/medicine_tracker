"""
Prescription OCR router.
Accepts an image upload, passes it to Gemini Vision, and returns parsed medication drafts.
"""
import json
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CaregiverPatient, Medication, Patient, PrescriptionScan, User
from app.schemas import (
    ConfirmScanRequest,
    ExtractedMedication,
    MedicationAddResponse,
    MedicationOut,
    PrescriptionScanOut,
)
from app.services.drug_resolver import resolve_drug
from app.services.interaction import check_new_medication_interactions
from app.config import settings

router = APIRouter(prefix="/patients", tags=["Prescription OCR"])
logger = logging.getLogger(__name__)


async def _require_patient_access(patient_id, current_user, db) -> Patient:
    stmt = (
        select(Patient)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Patient.id)
        .where(Patient.id == patient_id, CaregiverPatient.caregiver_id == current_user.id)
    )
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


@router.post("/{patient_id}/prescriptions/scan", response_model=PrescriptionScanOut)
async def scan_prescription(
    patient_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a prescription image. Gemini Vision extracts medication data.
    Returns a PrescriptionScan record with extracted_data to review in the UI.
    """
    await _require_patient_access(patient_id, current_user, db)

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API key not configured.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10 MB.")

    # Call Gemini Vision
    extracted = await _extract_medications_from_image(content, file.content_type or "image/jpeg")

    # Save to DB — image stored as base64 data URI for simplicity
    # (In production, upload to Cloudinary first)
    import base64
    image_b64 = base64.b64encode(content).decode()
    image_url = f"data:{file.content_type};base64,{image_b64[:100]}..."  # truncated for DB

    scan = PrescriptionScan(
        patient_id=patient_id,
        uploaded_by=current_user.id,
        image_url=f"upload:{file.filename}",
        extracted_data={"medications": [m.model_dump() for m in extracted]},
        reviewed=False,
    )
    db.add(scan)
    await db.flush()
    await db.refresh(scan)
    return scan


async def _extract_medications_from_image(image_bytes: bytes, mime_type: str) -> List[ExtractedMedication]:
    """Sends image to Gemini Vision and parses the response."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)

        prompt = (
            "You are a medical prescription reader. Extract all medications from this prescription image. "
            "For each medication, extract: name, dose_value (number only), dose_unit (mg/ml/tablet/etc), "
            "frequency_per_day (number; 1=once, 2=twice, 0.5=alternate days), and any notes. "
            "Return strictly as JSON: {\"medications\": [{\"name\": ..., \"dose_value\": ..., "
            "\"dose_unit\": ..., \"frequency_per_day\": ..., \"notes\": ...}]}. "
            "If a field is unclear, use null."
        )

        response = await client.aio.models.generate_content(
            model="gemini-1.5-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        data = json.loads(response.text)
        meds = data.get("medications", [])
        return [ExtractedMedication(**m) for m in meds if m.get("name")]

    except Exception as e:
        logger.error(f"Gemini OCR extraction failed: {e}")
        return []


@router.post("/{patient_id}/prescriptions/{scan_id}/confirm", response_model=List[MedicationAddResponse])
async def confirm_scan(
    patient_id: uuid.UUID,
    scan_id: uuid.UUID,
    body: ConfirmScanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Caregiver confirms the extracted medications from a scan.
    Bulk-adds them to the patient's medication list with interaction checks.
    """
    await _require_patient_access(patient_id, current_user, db)

    # Mark scan as reviewed
    stmt = select(PrescriptionScan).where(PrescriptionScan.id == scan_id)
    result = await db.execute(stmt)
    scan = result.scalar_one_or_none()
    if scan:
        scan.reviewed = True

    responses = []
    for med_data in body.medications:
        resolution = await resolve_drug(med_data.name)
        med = Medication(
            patient_id=patient_id,
            **med_data.model_dump(),
            rxcui=resolution["rxcui"],
            resolved_generic_names=resolution["generic_names"],
            resolution_source=resolution["source"],
            resolution_confidence=resolution["confidence"],
        )
        db.add(med)
        await db.flush()
        await db.refresh(med)

        warnings = []
        if resolution["rxcui"]:
            warnings = await check_new_medication_interactions(
                new_med_name=med_data.name,
                new_rxcui=resolution["rxcui"],
                new_generic_names=resolution.get("generic_names", []),
                patient_id=patient_id,
                session=db,
            )

        responses.append(
            MedicationAddResponse(
                medication=MedicationOut.model_validate(med),
                interaction_warnings=warnings,
            )
        )

    return responses
