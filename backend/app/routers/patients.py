import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CaregiverPatient, Patient, User
from app.schemas import (
    AddCaregiverRequest,
    CaregiverOut,
    GenerateLinkTokenResponse,
    PatientCreate,
    PatientOut,
    PatientUpdate,
)
from app.services.auth_service import create_link_token

router = APIRouter(prefix="/patients", tags=["Patients"])


async def _require_patient_access(
    patient_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Patient:
    """Ensures the current user is a caregiver for the given patient."""
    stmt = (
        select(Patient)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Patient.id)
        .where(
            Patient.id == patient_id,
            CaregiverPatient.caregiver_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.get("/", response_model=List[PatientOut])
async def list_patients(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Patient)
        .join(CaregiverPatient, CaregiverPatient.patient_id == Patient.id)
        .where(CaregiverPatient.caregiver_id == current_user.id)
        .order_by(Patient.full_name)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    body: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = Patient(**body.model_dump())
    db.add(patient)
    await db.flush()

    # Link the creator as primary caregiver
    link = CaregiverPatient(
        caregiver_id=current_user.id,
        patient_id=patient.id,
        role="primary",
    )
    db.add(link)
    await db.flush()
    await db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _require_patient_access(patient_id, current_user, db)


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await _require_patient_access(patient_id, current_user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    await db.flush()
    await db.refresh(patient)
    return patient


@router.post("/{patient_id}/caregivers", status_code=status.HTTP_201_CREATED)
async def add_caregiver(
    patient_id: uuid.UUID,
    body: AddCaregiverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allows a primary caregiver to invite another caregiver by email."""
    await _require_patient_access(patient_id, current_user, db)

    # Look up the new caregiver by email
    stmt = select(User).where(User.email == body.caregiver_email)
    result = await db.execute(stmt)
    new_caregiver = result.scalar_one_or_none()
    if not new_caregiver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with email '{body.caregiver_email}'.",
        )

    # Check if already linked
    existing_stmt = select(CaregiverPatient).where(
        (CaregiverPatient.caregiver_id == new_caregiver.id)
        & (CaregiverPatient.patient_id == patient_id)
    )
    existing = await db.execute(existing_stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Caregiver already linked.")

    db.add(CaregiverPatient(
        caregiver_id=new_caregiver.id,
        patient_id=patient_id,
        role=body.role,
    ))
    return {"detail": f"Caregiver '{new_caregiver.full_name}' added successfully."}


@router.get("/{patient_id}/caregivers", response_model=List[CaregiverOut])
async def list_patient_caregivers(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists all caregivers linked to this patient."""
    await _require_patient_access(patient_id, current_user, db)
    
    stmt = (
        select(User.id, User.email, User.full_name, CaregiverPatient.role)
        .join(CaregiverPatient, CaregiverPatient.caregiver_id == User.id)
        .where(CaregiverPatient.patient_id == patient_id)
        .order_by(User.full_name)
    )
    result = await db.execute(stmt)
    
    # Map raw rows to CaregiverOut dicts
    caregivers = []
    for row in result.all():
        caregivers.append(
            CaregiverOut(
                id=row[0],
                email=row[1],
                full_name=row[2],
                role=row[3],
            )
        )
    return caregivers



@router.post("/{patient_id}/link-token", response_model=GenerateLinkTokenResponse)
async def generate_link_token(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates a short-lived 6-digit code for a patient to link their Telegram account."""
    await _require_patient_access(patient_id, current_user, db)
    from app.services.auth_service import generate_short_link_code
    token = generate_short_link_code(f"patient:{patient_id}")
    return GenerateLinkTokenResponse(token=token)


@router.post("/me/link-token", response_model=GenerateLinkTokenResponse)
async def generate_caregiver_link_token(
    current_user: User = Depends(get_current_user),
):
    """Generates a short-lived 6-digit code for the caregiver to link their own Telegram account."""
    from app.services.auth_service import generate_short_link_code
    token = generate_short_link_code(f"caregiver:{current_user.id}")
    return GenerateLinkTokenResponse(token=token)

