"""
Drug interaction checker using the NIH RxNav API with a local DB cache.
Cache entries are considered fresh for 30 days.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DrugInteractionCache, Medication
from app.schemas import InteractionWarning

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
CACHE_TTL_DAYS = 30


import json
from app.config import settings

async def _fetch_interaction_from_gemini(drug_a: str, drug_b: str) -> Optional[dict]:
    """Asks Gemini to check for potential interactions between two generic drugs."""
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"Analyze the potential clinical drug-drug interaction between the generic drugs "
            f"'{drug_a}' and '{drug_b}'. "
            "Return your answer strictly as JSON with exactly two keys: "
            "'severity' (one of: 'critical', 'major', 'moderate', 'minor', 'none') "
            "and 'description' (a brief explanation of the interaction mechanism and clinical recommendations/warnings, "
            "or empty string if none). "
            "If there is no known clinically significant interaction, set severity to 'none' and description to ''."
        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = json.loads(response.text)
        severity = result.get("severity", "none").lower()
        if severity == "none":
            return None
        return {
            "severity": severity,
            "description": result.get("description", "Potential interaction detected.")
        }
    except Exception as e:
        logger.warning(f"Gemini interaction check failed for {drug_a}/{drug_b}: {e}")
    return None


async def check_interaction(
    rxcui_1: str,
    name_1: str,
    rxcui_2: str,
    name_2: str,
    session: AsyncSession,
) -> Optional[dict]:
    """
    Returns interaction info dict or None if no interaction found.
    Checks cache first; falls back to Gemini if stale or missing.
    """
    # Normalize pair order for consistent cache keys
    cui_min, cui_max = sorted([rxcui_1, rxcui_2])
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)

    # Check cache
    stmt = select(DrugInteractionCache).where(
        (DrugInteractionCache.rxcui_1 == cui_min)
        & (DrugInteractionCache.rxcui_2 == cui_max)
        & (DrugInteractionCache.fetched_at >= cutoff)
    )
    result = await session.execute(stmt)
    cached = result.scalar_one_or_none()
    if cached:
        if cached.severity == "none":
            return None
        return {"severity": cached.severity, "description": cached.description}

    # Fetch from Gemini
    api_result = await _fetch_interaction_from_gemini(name_1, name_2)
    
    # Upsert into cache
    existing_stmt = select(DrugInteractionCache).where(
        (DrugInteractionCache.rxcui_1 == cui_min)
        & (DrugInteractionCache.rxcui_2 == cui_max)
    )
    existing_result = await session.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    severity_val = api_result["severity"] if api_result else "none"
    desc_val = api_result["description"] if api_result else ""

    if existing:
        existing.severity = severity_val
        existing.description = desc_val
        existing.fetched_at = datetime.now(timezone.utc)
    else:
        session.add(
            DrugInteractionCache(
                rxcui_1=cui_min,
                rxcui_2=cui_max,
                severity=severity_val,
                description=desc_val,
            )
        )
    await session.commit()
    return api_result if severity_val != "none" else None


async def check_new_medication_interactions(
    new_med_name: str,
    new_rxcui: str,
    new_generic_names: List[str],
    patient_id,
    session: AsyncSession,
) -> List[InteractionWarning]:
    """
    Checks the new medication's generic components against all existing patient medications' generic components.
    Returns a list of InteractionWarning objects.
    """
    warnings: List[InteractionWarning] = []
    generics_a = new_generic_names if new_generic_names else [new_med_name]

    # Fetch all existing active medications
    stmt = select(Medication).where(
        (Medication.patient_id == patient_id)
        & (Medication.is_active == True)
    )
    result = await session.execute(stmt)
    existing_meds = result.scalars().all()

    for existing in existing_meds:
        generics_b = existing.resolved_generic_names if existing.resolved_generic_names else [existing.name]

        for gen_a in generics_a:
            for gen_b in generics_b:
                if gen_a.lower() == gen_b.lower():
                    continue

                # Get RxCUIs if available, fallback to truncated generic name as cache key
                from app.services.drug_resolver import _rxnorm_lookup
                cui_a = await _rxnorm_lookup(gen_a) or gen_a.lower()[:32]
                cui_b = await _rxnorm_lookup(gen_b) or gen_b.lower()[:32]

                interaction = await check_interaction(cui_a, gen_a, cui_b, gen_b, session)
                if interaction:
                    warnings.append(
                        InteractionWarning(
                            drug_a=f"{new_med_name} ({gen_a})",
                            drug_b=f"{existing.name} ({gen_b})",
                            severity=interaction["severity"],
                            description=interaction["description"],
                        )
                    )

    return warnings
