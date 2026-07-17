"""
4-Layer Indian Drug Name Resolution Pipeline:
  Layer 1: Direct RxNorm lookup
  Layer 2: Gemini AI brand-to-generic extraction (training knowledge)
  Layer 3: DuckDuckGo web search + Gemini parse (free, no API key needed)
  Layer 4: Unresolved fallback (manual entry flagged in UI)

Note: Google Custom Search JSON API is closed to new customers.
      Layer 3 now uses duckduckgo-search (pip install duckduckgo-search)
      which is completely free and requires no API key or signup.
"""
import asyncio
import json
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"

# Trusted Indian pharmacy / drug info sites to target in search
TRUSTED_DRUG_SITES = [
    "1mg.com",
    "medindia.net",
    "pharmeasy.in",
    "apollopharmacy.in",
    "drugbank.ca",
]


async def _rxnorm_lookup(drug_name: str) -> Optional[str]:
    """Returns RxCUI for the given drug name, or None if not found."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{RXNAV_BASE}/rxcui.json",
                params={"name": drug_name, "search": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                rxcui_list = data.get("idGroup", {}).get("rxnormId")
                if rxcui_list:
                    return rxcui_list[0]
    except Exception as e:
        logger.warning(f"RxNorm lookup failed for '{drug_name}': {e}")
    return None


async def _gemini_extract_generics(drug_name: str) -> dict:
    """
    Asks Gemini to identify the active pharmaceutical ingredients
    of an Indian brand-name drug using its training knowledge.
    Returns: {"generic_names": [...], "confidence": "high|medium|low"}
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"Identify the active pharmaceutical ingredients (generic name) of the Indian brand "
            f"medicine named '{drug_name}'. "
            "Return your answer strictly as JSON with exactly two keys: "
            "'generic_names' (an array of strings, use international non-proprietary names) "
            "and 'confidence' (one of: 'high', 'medium', 'low'). "
            "Use 'high' only if you are certain. "
            "If you are not certain, set confidence to 'low' and generic_names to an empty array."
        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = json.loads(response.text)
        return {
            "generic_names": result.get("generic_names", []),
            "confidence": result.get("confidence", "low"),
        }
    except Exception as e:
        logger.warning(f"Gemini extraction failed for '{drug_name}': {e}")
    return {"generic_names": [], "confidence": "low"}


async def _duckduckgo_search_composition(drug_name: str) -> str:
    """
    Uses DuckDuckGo Search (free, no API key) to find composition
    snippets from trusted Indian pharmacy websites.

    Requires: pip install duckduckgo-search
    """
    try:
        # Run synchronous ddgs in a thread to avoid blocking the event loop
        from duckduckgo_search import DDGS

        query = (
            f"{drug_name} composition active ingredients "
            f"site:{' OR site:'.join(TRUSTED_DRUG_SITES)}"
        )

        def _sync_search() -> str:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            snippets = " ".join(r.get("body", "") for r in results)
            return snippets

        snippets = await asyncio.get_event_loop().run_in_executor(None, _sync_search)
        return snippets

    except ImportError:
        logger.warning(
            "duckduckgo-search not installed. "
            "Run: pip install duckduckgo-search  to enable Layer 3."
        )
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed for '{drug_name}': {e}")
    return ""


async def _gemini_parse_composition_text(drug_name: str, text: str) -> dict:
    """Asks Gemini to extract generic names from unstructured web snippet text."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"Given the following web snippets about the Indian medicine '{drug_name}':\n\n"
            f"'{text[:3000]}'\n\n"  # Truncate to avoid token limits
            "Extract the active pharmaceutical ingredients (generic INN names). "
            "Return strictly as JSON: "
            "{\"generic_names\": [\"...\"], \"confidence\": \"high|medium|low\"}. "
            "Only include confirmed ingredients, not brand names."
        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = json.loads(response.text)
        return {
            "generic_names": result.get("generic_names", []),
            "confidence": result.get("confidence", "low"),
        }
    except Exception as e:
        logger.warning(f"Gemini parse failed: {e}")
    return {"generic_names": [], "confidence": "low"}


async def resolve_drug(drug_name: str) -> dict:
    """
    Main entry point for resolving a drug name to RxCUI.

    Pipeline:
      Layer 1 → RxNorm direct lookup (works for generic/INN names)
      Layer 2 → Gemini AI brand-to-generic (training knowledge, free)
      Layer 3 → DuckDuckGo search + Gemini parse (free, no API key)
      Layer 4 → Unresolved fallback (manual entry flag in UI)

    Returns a dict with:
      - resolved: bool
      - rxcui: str | None
      - generic_names: list[str]
      - source: 'rxnorm' | 'gemini' | 'web_search' | 'manual' | 'unresolved'
      - confidence: 'high' | 'medium' | 'low'
    """
    # ── Layer 1: Direct RxNorm lookup ──────────────────────────────────────
    rxcui = await _rxnorm_lookup(drug_name)
    if rxcui:
        logger.info(f"[Layer 1] Resolved '{drug_name}' via RxNorm → {rxcui}")
        return {
            "resolved": True, "rxcui": rxcui,
            "generic_names": [drug_name],
            "source": "rxnorm", "confidence": "high",
        }

    # ── Layer 2: Gemini AI brand-to-generic ────────────────────────────────
    if settings.gemini_api_key:
        gemini_result = await _gemini_extract_generics(drug_name)
        for generic in gemini_result["generic_names"]:
            rxcui = await _rxnorm_lookup(generic)
            if rxcui:
                logger.info(f"[Layer 2] Resolved '{drug_name}' via Gemini → {generic} → {rxcui}")
                return {
                    "resolved": True, "rxcui": rxcui,
                    "generic_names": gemini_result["generic_names"],
                    "source": "gemini",
                    "confidence": gemini_result["confidence"],
                }

        # ── Layer 3: DuckDuckGo search + Gemini parse ──────────────────────
        # Only fires if Gemini wasn't confident — avoids unnecessary API calls
        if gemini_result["confidence"] != "high":
            logger.info(f"[Layer 3] Gemini confidence low for '{drug_name}', trying DuckDuckGo...")
            snippets = await _duckduckgo_search_composition(drug_name)
            if snippets:
                web_result = await _gemini_parse_composition_text(drug_name, snippets)
                for generic in web_result["generic_names"]:
                    rxcui = await _rxnorm_lookup(generic)
                    if rxcui:
                        logger.info(
                            f"[Layer 3] Resolved '{drug_name}' via DuckDuckGo → {generic} → {rxcui}"
                        )
                        return {
                            "resolved": True, "rxcui": rxcui,
                            "generic_names": web_result["generic_names"],
                            "source": "web_search", "confidence": "medium",
                        }

    # ── Layer 4: Unresolved ────────────────────────────────────────────────
    logger.warning(f"[Layer 4] Could not resolve '{drug_name}' — flagged for manual entry.")
    return {
        "resolved": False, "rxcui": None,
        "generic_names": [], "source": "unresolved", "confidence": "low",
    }
