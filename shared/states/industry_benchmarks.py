"""Static industry Z-Score benchmark data for peer comparison.

Sources: Altman (1968, 1983, 2000), Blum (2014), industry-level studies.
These are APPROXIMATE medians intended only as prototype reference points.
The RS subgraph may supplement this with live competitor data later.

Benchmark version: static_benchmark_v1
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Industry categories
# The user or LLM should map the company's sector to one of these keys.
# ---------------------------------------------------------------------------

# (industry_key, formula_key, median_z, pct_safe, pct_grey, pct_distress, note)
_BENCHMARK_TABLE: dict[str, dict] = {
    # --- Manufacturing / Industrial ---
    "manufacturing": {
        "display_name": "Manufacturing",
        "formula": "original_public",   # Altman 1968 used for public; Z' for private
        "median_z": 2.30,
        "industry_safe_zone_pct": 0.40,
        "industry_grey_zone_pct": 0.35,
        "industry_distress_zone_pct": 0.25,
        "benchmark_z_safe": 2.99,       # Original Z thresholds
        "benchmark_z_distress": 1.81,
        "note": "Covers metals, chemicals, automotive, aerospace, machinery.",
    },
    "technology": {
        "display_name": "Technology / Software",
        "formula": "non_manufacturing",  # Z'' — no inventory/asset-heavy
        "median_z": 3.40,
        "industry_safe_zone_pct": 0.60,
        "industry_grey_zone_pct": 0.25,
        "industry_distress_zone_pct": 0.15,
        "benchmark_z_safe": 2.60,       # Z'' thresholds
        "benchmark_z_distress": 1.10,
        "note": "Covers SaaS, semiconductors, IT services, hardware.",
    },
    "healthcare": {
        "display_name": "Healthcare & Pharmaceuticals",
        "formula": "non_manufacturing",
        "median_z": 2.80,
        "industry_safe_zone_pct": 0.50,
        "industry_grey_zone_pct": 0.30,
        "industry_distress_zone_pct": 0.20,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Covers pharma, biotech, medical devices, hospitals.",
    },
    "retail": {
        "display_name": "Retail & Consumer Discretionary",
        "formula": "non_manufacturing",
        "median_z": 2.10,
        "industry_safe_zone_pct": 0.35,
        "industry_grey_zone_pct": 0.35,
        "industry_distress_zone_pct": 0.30,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Covers brick-and-mortar retail, e-commerce, apparel.",
    },
    "real_estate": {
        "display_name": "Real Estate",
        "formula": "non_manufacturing",
        "median_z": 1.90,
        "industry_safe_zone_pct": 0.30,
        "industry_grey_zone_pct": 0.35,
        "industry_distress_zone_pct": 0.35,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Covers REITs, developers, property management. Z-Score less applicable to REITs.",
    },
    "energy": {
        "display_name": "Energy & Natural Resources",
        "formula": "non_manufacturing",
        "median_z": 1.80,
        "industry_safe_zone_pct": 0.28,
        "industry_grey_zone_pct": 0.32,
        "industry_distress_zone_pct": 0.40,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Covers oil & gas, mining, renewables. Volatile due to commodity cycles.",
    },
    "utilities": {
        "display_name": "Utilities",
        "formula": "non_manufacturing",
        "median_z": 1.70,
        "industry_safe_zone_pct": 0.25,
        "industry_grey_zone_pct": 0.40,
        "industry_distress_zone_pct": 0.35,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Utilities carry structural high debt; Z-Score must be interpreted cautiously.",
    },
    "consumer_goods": {
        "display_name": "Consumer Goods / FMCG",
        "formula": "revised_private",
        "median_z": 2.20,
        "industry_safe_zone_pct": 0.38,
        "industry_grey_zone_pct": 0.32,
        "industry_distress_zone_pct": 0.30,
        "benchmark_z_safe": 2.90,       # Z' thresholds
        "benchmark_z_distress": 1.23,
        "note": "Covers food, beverages, household products.",
    },
    "telecommunications": {
        "display_name": "Telecommunications",
        "formula": "non_manufacturing",
        "median_z": 2.20,
        "industry_safe_zone_pct": 0.35,
        "industry_grey_zone_pct": 0.35,
        "industry_distress_zone_pct": 0.30,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Covers mobile operators, broadband, satellite.",
    },
    "financial_services": {
        "display_name": "Financial Services",
        "formula": "non_manufacturing",
        "median_z": None,               # Z-Score not designed for financial firms
        "industry_safe_zone_pct": None,
        "industry_grey_zone_pct": None,
        "industry_distress_zone_pct": None,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Z-Score is NOT recommended for banks/insurers. Use other metrics (CET1, NPL ratio).",
    },
    "transportation": {
        "display_name": "Transportation & Logistics",
        "formula": "non_manufacturing",
        "median_z": 2.00,
        "industry_safe_zone_pct": 0.32,
        "industry_grey_zone_pct": 0.35,
        "industry_distress_zone_pct": 0.33,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Aviation, shipping, freight, rail.",
    },
    "media_entertainment": {
        "display_name": "Media & Entertainment",
        "formula": "non_manufacturing",
        "median_z": 2.50,
        "industry_safe_zone_pct": 0.42,
        "industry_grey_zone_pct": 0.30,
        "industry_distress_zone_pct": 0.28,
        "benchmark_z_safe": 2.60,
        "benchmark_z_distress": 1.10,
        "note": "Broadcasting, streaming, gaming, publishing.",
    },
}

# Canonical list of industry sector keys for validation / dropdown
INDUSTRY_SECTOR_KEYS = list(_BENCHMARK_TABLE.keys())

# Default fallback (used when exact match not found)
_DEFAULT_BENCHMARK: dict = {
    "display_name": "General / Other",
    "formula": "revised_private",
    "median_z": 2.20,
    "industry_safe_zone_pct": 0.38,
    "industry_grey_zone_pct": 0.32,
    "industry_distress_zone_pct": 0.30,
    "benchmark_z_safe": 2.90,
    "benchmark_z_distress": 1.23,
    "note": "No industry-specific benchmark available. Z' thresholds applied as default.",
}


def get_benchmark(industry_sector: str | None) -> dict:
    """Return benchmark dict for a given industry sector string.

    Does a case-insensitive partial match against known keys and display names.
    Falls back to _DEFAULT_BENCHMARK if no match is found.
    """
    if not industry_sector:
        return {**_DEFAULT_BENCHMARK, "_sector_key": "unknown"}

    query = industry_sector.strip().lower().replace(" ", "_").replace("-", "_")

    # Exact key match first
    if query in _BENCHMARK_TABLE:
        return {**_BENCHMARK_TABLE[query], "_sector_key": query}

    # Partial match against keys
    for key, data in _BENCHMARK_TABLE.items():
        if query in key or key in query:
            return {**data, "_sector_key": key}

    # Partial match against display names
    for key, data in _BENCHMARK_TABLE.items():
        if query in data["display_name"].lower().replace(" ", "_"):
            return {**data, "_sector_key": key}

    # Fallback
    return {**_DEFAULT_BENCHMARK, "_sector_key": "unknown"}
