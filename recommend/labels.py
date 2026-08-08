"""How assets and structures read inside a sentence.

Machine-generated names get casing and articles wrong — "a ai compute project",
"spv" — and a reader notices that before they notice the analysis. One table,
shared by the gates and the rationale, so the two never disagree.
"""

from __future__ import annotations

ASSET_LABELS: dict[str, str] = {
    "SOLAR": "solar",
    "SOLAR_PLUS_STORAGE": "solar-plus-storage",
    "STORAGE": "standalone storage",
    "WIND": "onshore wind",
    "DATA_CENTRE": "data centre",
    "AI_COMPUTE": "AI compute",
    "RNG": "RNG",
    "GAS": "gas-fired",
    "TRANSMISSION": "transmission",
    "PORTFOLIO": "portfolio",
}


def asset_label(asset_type: str) -> str:
    return ASSET_LABELS.get(asset_type, asset_type.replace("_", " ").lower())


def article(word: str) -> str:
    return "An" if word[:1].upper() in "AEIOU" else "A"


def asset_phrase(asset_type: str) -> str:
    """e.g. "An AI compute project", "A solar-plus-storage project"."""
    label = asset_label(asset_type)
    return f"{article(label)} {label} project"
