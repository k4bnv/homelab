"""Use the Claude API to pull structured hardware specs and likely defects out
of a listing's free-text description.

Costs an API call per listing, so main.py only calls this on listings that
already survived the keyword + price filters, not on the whole search result.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("scraper.enrich")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

EXTRACTION_PROMPT = (
    "Je krijgt de beschrijving van een tweedehands laptop-advertentie van Marktplaats.nl. "
    "Extract the hardware specs you can find (CPU, RAM, SSD/storage, screen size/resolution) "
    "and flag likely defects or red flags mentioned or implied in the text (e.g. 'voor onderdelen', "
    "scratches, battery issues, missing charger, cracked screen, water damage). "
    "If a field isn't mentioned, leave it null. Be conservative with likely_defects: only include "
    "things the text actually supports, don't invent problems."
)


class LaptopSpecs(BaseModel):
    cpu: Optional[str] = None
    ram_gb: Optional[float] = None
    ssd_gb: Optional[float] = None
    screen: Optional[str] = None
    likely_defects: list[str] = Field(default_factory=list)
    confidence_notes: Optional[str] = None


_TOOL_SCHEMA = {
    "name": "extract_laptop_specs",
    "description": "Record extracted laptop hardware specs and likely defects from a listing description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cpu": {"type": ["string", "null"], "description": "CPU model, e.g. 'Intel Core i5-8350U'"},
            "ram_gb": {"type": ["number", "null"], "description": "RAM size in GB"},
            "ssd_gb": {"type": ["number", "null"], "description": "SSD/storage size in GB"},
            "screen": {"type": ["string", "null"], "description": "Screen size and/or resolution, e.g. '14\" FHD'"},
            "likely_defects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short phrases describing defects/red flags actually supported by the text",
            },
            "confidence_notes": {
                "type": ["string", "null"],
                "description": "One short sentence on how confident this extraction is",
            },
        },
        "required": ["likely_defects"],
    },
}


def enrich_description(
    description_raw: Optional[str],
    *,
    model: str = DEFAULT_MODEL,
    client=None,
) -> Optional[LaptopSpecs]:
    """Returns None (and logs why) instead of raising, so a single failed
    enrichment never aborts the whole run."""
    if not description_raw or not description_raw.strip():
        return None

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed; skipping enrichment")
        return None

    if client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set; skipping enrichment")
            return None
        client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "extract_laptop_specs"},
            messages=[
                {
                    "role": "user",
                    "content": f"{EXTRACTION_PROMPT}\n\n---\n{description_raw}\n---",
                }
            ],
        )
    except Exception as exc:  # network/auth/rate-limit errors from the SDK
        logger.error("Claude enrichment call failed: %s", exc)
        return None

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "extract_laptop_specs":
            try:
                return LaptopSpecs.model_validate(block.input)
            except Exception as exc:
                logger.error("Failed to validate Claude enrichment output: %s", exc)
                return None

    logger.warning("Claude response had no tool_use block for extract_laptop_specs")
    return None
