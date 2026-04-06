"""LLM chat assistant service for the Results page.

Builds a system prompt from the full case state and forwards the conversation
to the configured LLM via the shared OpenRouter client.
"""

from __future__ import annotations


def build_case_context(case: dict) -> str:
    """Summarise the key case data into a compact system prompt."""
    company = case.get("company") or {}
    name = company.get("company_name", "Unknown company")
    sector = company.get("industry_sector") or "unspecified sector"
    ctype = company.get("company_type", "private")

    tl = case.get("frd_traffic_light") or "not yet assessed"
    status = case.get("status", "unknown")

    # Z-score
    ff = case.get("financial_features") or {}
    zs = ff.get("current_z_score") or {}
    z_score_txt = ""
    if zs.get("score") is not None:
        z_score_txt = (
            f"Altman Z-Score: {zs['score']:.2f} (zone: {zs.get('zone', 'unknown')}, "
            f"formula: {zs.get('formula_used', 'unknown')}). "
        )

    # Ratios
    ratios = ff.get("ratios") or {}
    ratio_lines = []
    for k, label in [
        ("current_ratio", "Current ratio"),
        ("debt_to_equity", "D/E ratio"),
        ("net_margin", "Net margin"),
        ("interest_coverage", "Interest coverage"),
    ]:
        v = ratios.get(k)
        if v is not None:
            ratio_lines.append(f"{label}: {v:.2f}")
    ratios_txt = "; ".join(ratio_lines) if ratio_lines else "not available"

    # Signals
    sis = case.get("sis_output") or {}
    signals = sis.get("signals") or []
    high_sigs = [s for s in signals if s.get("severity") == "high"]
    sig_txt = ""
    if signals:
        sig_txt = (
            f"SIS extracted {len(signals)} signals "
            f"({len(high_sigs)} high-severity). "
        )
        if high_sigs:
            tops = high_sigs[:3]
            sig_txt += "Top risks: " + "; ".join(
                f"{s.get('event_type','?')}/{s.get('event_subtype','?')}"
                for s in tops
            ) + ". "

    # Report narrative (truncate to keep context window manageable)
    frd = case.get("frd_output") or {}
    narrative = frd.get("report_narrative") or ""
    if narrative and len(narrative) > 2000:
        narrative = narrative[:2000] + "… [truncated]"
    narrative_txt = f"\n\nAnalyst report excerpt:\n{narrative}" if narrative else ""

    # Criteria
    risk_score = frd.get("risk_score") or {}
    flags = risk_score.get("flags") or []
    flags_txt = ""
    if flags:
        flags_txt = "Risk flags: " + "; ".join(flags[:5]) + ". "

    system = (
        f"You are an expert credit risk analyst assistant. "
        f"You have been provided with the full analysis for {name} "
        f"({ctype}, {sector}). "
        f"Current pipeline status: {status}. "
        f"Traffic light verdict: {tl.upper() if tl != 'not yet assessed' else tl}. "
        f"{z_score_txt}"
        f"Key ratios — {ratios_txt}. "
        f"{sig_txt}"
        f"{flags_txt}"
        f"Answer questions about this specific company's credit profile. "
        f"Be concise, precise, and professional. "
        f"When quoting numbers, use the data provided above."
        f"{narrative_txt}"
        "\n\n"
        "COMPLIANCE AND SCOPE CONSTRAINTS — MANDATORY:\n"
        "- You are an internal credit risk analysis tool for authorised UBS analysts only.\n"
        "- You MUST NOT provide investment advice, buy/sell/hold recommendations, "
        "or price/return/rating predictions.\n"
        "- You MUST NOT recommend any specific financial instrument, security, or credit action.\n"
        "- Every substantive claim about creditworthiness must be caveated as preliminary "
        "AI-generated analysis subject to human review.\n"
        "- If a user asks for investment advice, a credit rating, or a future price or return "
        "prediction, politely decline and redirect them to consult a qualified professional.\n"
        "- Do not speculate beyond the data provided in the case context.\n"
        "- Always note material data gaps or low-confidence signals as limitations."
    )
    return system


def chat_with_case(case: dict, message: str, history: list[dict]) -> str:
    """Send a chat message in the context of a case and return the reply.

    Args:
        case: Full CaseState dict from the database.
        message: Latest user message.
        history: Prior turns as [{"role": "user"|"assistant", "content": str}, ...].

    Returns:
        LLM reply string.
    """
    from shared.llm import get_client, MODEL_FRD

    client = get_client()
    system = build_case_context(case)

    messages: list[dict] = [{"role": "system", "content": system}]
    # Only include the last 10 turns to avoid context overflow
    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    resp = client.chat.completions.create(
        model=MODEL_FRD,
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )
    return resp.choices[0].message.content or ""
