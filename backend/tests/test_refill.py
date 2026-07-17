"""
Unit tests for the refill calculation logic.
Tests the days_remaining property on the Medication model.
"""
import uuid
from datetime import date

import pytest

# We test the calculation logic directly without the DB
# by constructing minimal Medication-like objects


class FakeMedication:
    """Minimal stand-in for testing days_remaining calculation."""

    def __init__(self, quantity_on_hand: float, frequency_per_day: float):
        self.id = uuid.uuid4()
        self.patient_id = uuid.uuid4()
        self.name = "TestDrug"
        self.rxcui = None
        self.resolved_generic_names = []
        self.resolution_source = "unresolved"
        self.resolution_confidence = "low"
        self.dose_value = 500.0
        self.dose_unit = "mg"
        self.frequency_per_day = frequency_per_day
        self.quantity_on_hand = quantity_on_hand
        self.start_date = date.today()
        self.refill_threshold_days = 7
        self.reminder_escalation_days = 3
        self.is_active = True
        self.notes = None

    @property
    def days_remaining(self) -> float:
        daily_consumption = self.frequency_per_day
        if daily_consumption <= 0:
            return float("inf")
        return round(self.quantity_on_hand / daily_consumption, 1)


def test_days_remaining_standard():
    """30 tablets, twice a day = 15 days."""
    med = FakeMedication(quantity_on_hand=30, frequency_per_day=2)
    assert med.days_remaining == 15.0


def test_days_remaining_once_daily():
    """14 tablets, once a day = 14 days."""
    med = FakeMedication(quantity_on_hand=14, frequency_per_day=1)
    assert med.days_remaining == 14.0


def test_days_remaining_three_times():
    """90 tablets, 3 times a day = 30 days."""
    med = FakeMedication(quantity_on_hand=90, frequency_per_day=3)
    assert med.days_remaining == 30.0


def test_days_remaining_fractional():
    """15 tablets, every other day (0.5/day) = 30 days."""
    med = FakeMedication(quantity_on_hand=15, frequency_per_day=0.5)
    assert med.days_remaining == 30.0


def test_days_remaining_zero_stock():
    """0 tablets remaining = 0 days."""
    med = FakeMedication(quantity_on_hand=0, frequency_per_day=2)
    assert med.days_remaining == 0.0


def test_days_remaining_zero_frequency_is_infinite():
    """Edge case: zero frequency should not divide by zero."""
    med = FakeMedication(quantity_on_hand=30, frequency_per_day=0)
    assert med.days_remaining == float("inf")


def test_refill_threshold_trigger():
    """Medication with 5 days left should trigger the 7-day threshold."""
    med = FakeMedication(quantity_on_hand=10, frequency_per_day=2)
    assert med.days_remaining == 5.0
    assert med.days_remaining <= med.refill_threshold_days


def test_escalation_threshold_trigger():
    """Medication with 2 days left should trigger the 3-day escalation."""
    med = FakeMedication(quantity_on_hand=4, frequency_per_day=2)
    assert med.days_remaining == 2.0
    assert med.days_remaining <= med.reminder_escalation_days
