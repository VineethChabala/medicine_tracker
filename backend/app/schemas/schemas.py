from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth Schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    telegram_chat_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Patient Schemas
# ---------------------------------------------------------------------------
class PatientCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    age: Optional[int] = Field(None, ge=0, le=150)
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    age: Optional[int] = Field(None, ge=0, le=150)
    notes: Optional[str] = None
    telegram_chat_id: Optional[int] = None


class PatientOut(BaseModel):
    id: uuid.UUID
    full_name: str
    age: Optional[int] = None
    telegram_chat_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddCaregiverRequest(BaseModel):
    caregiver_email: EmailStr
    role: str = "secondary"


class CaregiverOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Medication Schemas
# ---------------------------------------------------------------------------
class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dose_value: float = Field(gt=0)
    dose_unit: str = Field(min_length=1, max_length=32)
    frequency_per_day: float = Field(gt=0)
    quantity_on_hand: float = Field(ge=0)
    start_date: date
    refill_threshold_days: int = Field(default=7, ge=1)
    reminder_escalation_days: int = Field(default=3, ge=1)
    notes: Optional[str] = None


class MedicationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    dose_value: Optional[float] = Field(None, gt=0)
    dose_unit: Optional[str] = None
    frequency_per_day: Optional[float] = Field(None, gt=0)
    quantity_on_hand: Optional[float] = Field(None, ge=0)
    refill_threshold_days: Optional[int] = Field(None, ge=1)
    reminder_escalation_days: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    # Allow manual resolution fallback
    resolved_generic_names: Optional[List[str]] = None
    rxcui: Optional[str] = None


class MedicationOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    name: str
    rxcui: Optional[str] = None
    resolved_generic_names: List[str] = []
    resolution_source: str
    resolution_confidence: str
    dose_value: float
    dose_unit: str
    frequency_per_day: float
    quantity_on_hand: float
    start_date: date
    refill_threshold_days: int
    reminder_escalation_days: int
    days_remaining: float
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Interaction Schemas
# ---------------------------------------------------------------------------
class InteractionWarning(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    description: str


class MedicationAddResponse(BaseModel):
    medication: MedicationOut
    interaction_warnings: List[InteractionWarning] = []


# ---------------------------------------------------------------------------
# Prescription Scan Schemas
# ---------------------------------------------------------------------------
class ExtractedMedication(BaseModel):
    name: str
    dose_value: Optional[float] = None
    dose_unit: Optional[str] = None
    frequency_per_day: Optional[float] = None
    notes: Optional[str] = None


class PrescriptionScanOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    image_url: str
    extracted_data: Any
    reviewed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfirmScanRequest(BaseModel):
    medications: List[MedicationCreate]


# ---------------------------------------------------------------------------
# Telegram Link Schemas
# ---------------------------------------------------------------------------
class GenerateLinkTokenResponse(BaseModel):
    token: str
    expires_in_minutes: int = 30
    bot_username: Optional[str] = None
