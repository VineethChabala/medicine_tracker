import uuid
from datetime import datetime, date
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, BigInteger, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now_utc():
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Users (Caregivers)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(Text, nullable=False)
    full_name = Column(String(255), nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = now_utc()
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    patient_links = relationship("CaregiverPatient", back_populates="caregiver", cascade="all, delete-orphan")
    prescription_scans = relationship("PrescriptionScan", back_populates="uploaded_by_user")


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
class Patient(Base):
    __tablename__ = "patients"

    id = uuid_pk()
    full_name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    telegram_chat_id = Column(BigInteger, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = now_utc()

    # Relationships
    caregiver_links = relationship("CaregiverPatient", back_populates="patient", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="patient", cascade="all, delete-orphan")
    prescription_scans = relationship("PrescriptionScan", back_populates="patient", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Caregiver ↔ Patient (Many-to-Many join table)
# ---------------------------------------------------------------------------
class CaregiverPatient(Base):
    __tablename__ = "caregiver_patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    caregiver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), default="primary", nullable=False)  # 'primary' | 'secondary'
    created_at = now_utc()

    __table_args__ = (UniqueConstraint("caregiver_id", "patient_id", name="uq_caregiver_patient"),)

    caregiver = relationship("User", back_populates="patient_links")
    patient = relationship("Patient", back_populates="caregiver_links")


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------
class Medication(Base):
    __tablename__ = "medications"

    id = uuid_pk()
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)

    # Drug resolution
    rxcui = Column(String(32), nullable=True, index=True)
    resolved_generic_names = Column(JSONB, default=list)
    resolution_source = Column(String(64), default="unresolved")  # rxnorm | gemini | web_search | manual | unresolved
    resolution_confidence = Column(String(16), default="low")  # high | medium | low

    # Dosage
    dose_value = Column(Float, nullable=False)
    dose_unit = Column(String(32), nullable=False)  # mg | ml | tablet | capsule
    frequency_per_day = Column(Float, nullable=False)  # 2.0 = twice/day

    # Inventory
    quantity_on_hand = Column(Float, nullable=False)

    # Schedule
    start_date = Column(Date, nullable=False)
    refill_threshold_days = Column(Integer, default=7, nullable=False)
    reminder_escalation_days = Column(Integer, default=3, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = now_utc()
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    patient = relationship("Patient", back_populates="medications")
    reminder_logs = relationship("RefillReminderLog", back_populates="medication", cascade="all, delete-orphan")

    @property
    def days_remaining(self) -> float:
        """Calculates projected days of medication remaining."""
        daily_consumption = self.frequency_per_day  # doses per day = tablets/units used
        if daily_consumption <= 0:
            return float("inf")
        return round(self.quantity_on_hand / daily_consumption, 1)


# ---------------------------------------------------------------------------
# Drug Interaction Cache
# ---------------------------------------------------------------------------
class DrugInteractionCache(Base):
    __tablename__ = "drug_interactions_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rxcui_1 = Column(String(32), nullable=False)
    rxcui_2 = Column(String(32), nullable=False)
    severity = Column(String(32), nullable=False)  # contraindicated | major | moderate | minor
    description = Column(Text, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("rxcui_1", "rxcui_2", name="uq_interaction_pair"),)


# ---------------------------------------------------------------------------
# Refill Reminder Log
# ---------------------------------------------------------------------------
class RefillReminderLog(Base):
    __tablename__ = "refill_reminders_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medication_id = Column(UUID(as_uuid=True), ForeignKey("medications.id", ondelete="CASCADE"), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    chat_id = Column(BigInteger, nullable=False)
    days_remaining_at_send = Column(Float, nullable=False)
    status = Column(String(16), nullable=False)  # sent | failed

    medication = relationship("Medication", back_populates="reminder_logs")


# ---------------------------------------------------------------------------
# Prescription Scans
# ---------------------------------------------------------------------------
class PrescriptionScan(Base):
    __tablename__ = "prescription_scans"

    id = uuid_pk()
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(Text, nullable=False)
    extracted_data = Column(JSONB, default=dict)
    reviewed = Column(Boolean, default=False, nullable=False)
    created_at = now_utc()

    patient = relationship("Patient", back_populates="prescription_scans")
    uploaded_by_user = relationship("User", back_populates="prescription_scans")
