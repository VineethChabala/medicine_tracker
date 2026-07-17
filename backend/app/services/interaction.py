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


async def _fetch_interaction_from_api(rxcui_1: str, rxcui_2: str) -> Optional[dict]:
    """Calls RxNav interaction API for a specific RXCUI pair."""
    url = f"{RXNAV_BASE}/interaction/list.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"rxcuis": f"{rxcui_1}+{rxcui_2}"})
            if resp.status_code != 200:
                return None
            data = resp.json()
            groups = data.get("fullInteractionTypeGroup", [])
            for group in groups:
                for fit in group.get("fullInteractionType", []):
                    for pair in fit.get("interactionPair", []):
                        severity = pair.get("severity", "moderate")
                        description = pair.get("description", "Potential interaction detected.")
                        return {"severity": severity, "description": description}
    except Exception as e:
        logger.warning(f"RxNav interaction API failed for {rxcui_1}/{rxcui_2}: {e}")
    return None


async def check_interaction(
    rxcui_1: str,
    rxcui_2: str,
    session: AsyncSession,
) -> Optional[dict]:
    """
    Returns interaction info dict or None if no interaction found.
    Checks cache first; falls back to live API if stale or missing.
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
        return {"severity": cached.severity, "description": cached.description}

    # Fetch from API
    api_result = await _fetch_interaction_from_api(cui_min, cui_max)
    if api_result:
        # Upsert into cache
        existing_stmt = select(DrugInteractionCache).where(
            (DrugInteractionCache.rxcui_1 == cui_min)
            & (DrugInteractionCache.rxcui_2 == cui_max)
        )
        existing_result = await session.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.severity = api_result["severity"]
            existing.description = api_result["description"]
            existing.fetched_at = datetime.now(timezone.utc)
        else:
            session.add(
                DrugInteractionCache(
                    rxcui_1=cui_min,
                    rxcui_2=cui_max,
                    severity=api_result["severity"],
                    description=api_result["description"],
                )
            )
        await session.commit()
        return api_result

    return None


async def check_new_medication_interactions(
    new_med_name: str,
    new_rxcui: str,
    patient_id,
    session: AsyncSession,
) -> List[InteractionWarning]:
    """
    Checks the new medication's RXCUI against all existing patient medications.
    Returns a list of InteractionWarning objects.
    """
    warnings: List[InteractionWarning] = []

    # Fetch all existing active medications with resolved RXCUIs
    stmt = select(Medication).where(
        (Medication.patient_id == patient_id)
        & (Medication.is_active == True)
        & (Medication.rxcui.isnot(None))
    )
    result = await session.execute(stmt)
    existing_meds = result.scalars().all()

    for existing in existing_meds:
        if existing.rxcui == new_rxcui:
            continue  # Same drug, skip

        interaction = await check_interaction(new_rxcui, existing.rxcui, session)
        if interaction:
            # Only surface major+ interactions or anything the API returns
            warnings.append(
                InteractionWarning(
                    drug_a=new_med_name,
                    drug_b=existing.name,
                    severity=interaction["severity"],
                    description=interaction["description"],
                )
            )

    return warnings
