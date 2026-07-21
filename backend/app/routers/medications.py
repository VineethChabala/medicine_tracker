import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CaregiverPatient, Medication, Patient, User
from app.schemas import (
    MedicationAddResponse,
    MedicationCreate,
    MedicationOut,
    MedicationUpdate,
)
from app.services.drug_resolver import resolve_drug
from app.services.interaction import check_new_medication_interactions

router = APIRouter(prefix="/patients", tags=["Medications"])


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


@router.get("/{patient_id}/medications", response_model=List[MedicationOut])
async def list_medications(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_patient_access(patient_id, current_user, db)
    stmt = (
        select(Medication)
        .where(Medication.patient_id == patient_id, Medication.is_active == True)
        .order_by(Medication.name)
    )
    result = await db.execute(stmt)
    meds = result.scalars().all()
    return meds


@router.post("/{patient_id}/medications", response_model=MedicationAddResponse, status_code=201)
async def add_medication(
    patient_id: uuid.UUID,
    body: MedicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_patient_access(patient_id, current_user, db)

    # Resolve the drug name to an RxCUI
    resolution = await resolve_drug(body.name)

    med = Medication(
        patient_id=patient_id,
        **body.model_dump(),
        rxcui=resolution["rxcui"],
        resolved_generic_names=resolution["generic_names"],
        resolution_source=resolution["source"],
        resolution_confidence=resolution["confidence"],
    )
    db.add(med)
    await db.flush()
    await db.refresh(med)

    # Check interactions if we have a resolved RxCUI
    warnings = []
    if resolution["rxcui"]:
        warnings = await check_new_medication_interactions(
            new_med_name=body.name,
            new_rxcui=resolution["rxcui"],
            new_generic_names=resolution.get("generic_names", []),
            patient_id=patient_id,
            session=db,
        )

    return MedicationAddResponse(medication=MedicationOut.model_validate(med), interaction_warnings=warnings)


@router.patch("/medications/{med_id}", response_model=MedicationOut)
async def update_medication(
    med_id: uuid.UUID,
    body: MedicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Medication)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Medication.patient_id)
        .where(Medication.id == med_id, CaregiverPatient.caregiver_id == current_user.id)
    )
    result = await db.execute(stmt)
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found.")

    updates = body.model_dump(exclude_unset=True)

    # If manual generic names provided, re-resolve from those
    if "resolved_generic_names" in updates and updates["resolved_generic_names"]:
        generics = updates["resolved_generic_names"]
        from app.services.drug_resolver import _rxnorm_lookup
        for g in generics:
            rxcui = await _rxnorm_lookup(g)
            if rxcui:
                updates["rxcui"] = rxcui
                updates["resolution_source"] = "manual"
                updates["resolution_confidence"] = "high"
                break

    for field, value in updates.items():
        setattr(med, field, value)

    await db.flush()
    await db.refresh(med)
    return med


@router.post("/medications/{med_id}/record-dose", response_model=MedicationOut)
async def record_dose(
    med_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record that one dose was taken, decrementing quantity_on_hand by 1."""
    stmt = (
        select(Medication)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Medication.patient_id)
        .where(Medication.id == med_id, CaregiverPatient.caregiver_id == current_user.id)
    )
    result = await db.execute(stmt)
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found.")

    if med.quantity_on_hand <= 0:
        raise HTTPException(status_code=400, detail="Quantity is already 0. Please refill first.")

    med.quantity_on_hand = max(0.0, med.quantity_on_hand - 1.0)
    await db.flush()
    await db.refresh(med)
    return med


@router.delete("/medications/{med_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_medication(
    med_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Medication)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Medication.patient_id)
        .where(Medication.id == med_id, CaregiverPatient.caregiver_id == current_user.id)
    )
    result = await db.execute(stmt)
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found.")

    med.is_active = False  # Soft delete
    await db.flush()
