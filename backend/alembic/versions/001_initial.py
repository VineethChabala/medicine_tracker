"""Initial schema — all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('hashed_password', sa.Text, nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_telegram_chat_id', 'users', ['telegram_chat_id'])

    # patients
    op.create_table(
        'patients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('age', sa.Integer, nullable=True),
        sa.Column('telegram_chat_id', sa.BigInteger, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_patients_telegram_chat_id', 'patients', ['telegram_chat_id'])

    # caregiver_patients
    op.create_table(
        'caregiver_patients',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('caregiver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(32), server_default='primary', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('caregiver_id', 'patient_id', name='uq_caregiver_patient'),
    )
    op.create_index('idx_caregiver_patients_patient', 'caregiver_patients', ['patient_id'])

    # medications
    op.create_table(
        'medications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('rxcui', sa.String(32), nullable=True),
        sa.Column('resolved_generic_names', postgresql.JSONB, server_default='[]'),
        sa.Column('resolution_source', sa.String(64), server_default='unresolved'),
        sa.Column('resolution_confidence', sa.String(16), server_default='low'),
        sa.Column('dose_value', sa.Float, nullable=False),
        sa.Column('dose_unit', sa.String(32), nullable=False),
        sa.Column('frequency_per_day', sa.Float, nullable=False),
        sa.Column('quantity_on_hand', sa.Float, nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('refill_threshold_days', sa.Integer, server_default='7', nullable=False),
        sa.Column('reminder_escalation_days', sa.Integer, server_default='3', nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_medications_patient', 'medications', ['patient_id'])
    op.create_index('idx_medications_rxcui', 'medications', ['rxcui'], postgresql_where=sa.text('rxcui IS NOT NULL'))

    # drug_interactions_cache
    op.create_table(
        'drug_interactions_cache',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('rxcui_1', sa.String(32), nullable=False),
        sa.Column('rxcui_2', sa.String(32), nullable=False),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('rxcui_1', 'rxcui_2', name='uq_interaction_pair'),
    )
    op.create_index('idx_interactions_pair', 'drug_interactions_cache', ['rxcui_1', 'rxcui_2'])

    # refill_reminders_log
    op.create_table(
        'refill_reminders_log',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('medication_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('medications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('chat_id', sa.BigInteger, nullable=False),
        sa.Column('days_remaining_at_send', sa.Float, nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
    )
    op.create_index('idx_reminders_log_med_date', 'refill_reminders_log', ['medication_id', 'sent_at'])

    # prescription_scans
    op.create_table(
        'prescription_scans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('image_url', sa.Text, nullable=False),
        sa.Column('extracted_data', postgresql.JSONB, server_default='{}'),
        sa.Column('reviewed', sa.Boolean, server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('prescription_scans')
    op.drop_table('refill_reminders_log')
    op.drop_table('drug_interactions_cache')
    op.drop_table('medications')
    op.drop_table('caregiver_patients')
    op.drop_table('patients')
    op.drop_table('users')
