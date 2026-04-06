"""Results Dashboard — traffic light, financials, signals, FRD report, AI chat."""

import json
import textwrap
import requests


def _html(s: str) -> str:
    """Strip common leading whitespace so triple-quoted HTML strings aren't
    parsed as Markdown indented code blocks by Streamlit."""
    return textwrap.dedent(s).strip()

api_base    = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

# ── Guard ─────────────────────────────────────────────────────────────────────
if not active_case:
    st.markdown("""
    <div style="text-align:center;padding:5rem 2rem;">
      <div style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:800;
                  color:#1c1b1b;margin-bottom:0.75rem;">No active case</div>
      <div style="color:#5f5e5e;font-size:0.9375rem;">
        Go to <strong>Case Entry</strong> to create or select a case first.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Load case data ────────────────────────────────────────────────────────────
case_data = None
try:
    r = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=10)
    if r.status_code == 200:
        case_data = r.json()
except Exception:
    pass

if case_data is None:
    st.error("Could not load case data. Check that the backend is running.")
    st.stop()

company  = case_data.get("company") or {}
name     = company.get("company_name", active_case)
sector   = (company.get("industry_sector") or "—").replace("_", " ").title()
ctype    = company.get("company_type", "private").title()
tl       = case_data.get("frd_traffic_light")
status   = case_data.get("status", "unknown")
ff       = case_data.get("financial_features") or {}
sis_data = case_data.get("sis_output") or {}
frd_data = case_data.get("frd_output") or {}


def _fmt(val, fmt=".2f", fallback="—"):
    if val is None:
        return fallback
    try:
        return format(float(val), fmt)
    except Exception:
        return fallback


_TL_COLOR = {"green": "#15803d", "amber": "#d97706", "red": "#b70100"}
_TL_LABEL = {"green": "Low Risk",      "amber": "Moderate Risk", "red": "High Risk"}
_TL_BG    = {"green": "rgba(21,128,61,0.08)",
             "amber": "rgba(180,120,0,0.08)",
             "red":   "rgba(183,1,0,0.08)"}

tl_color = _TL_COLOR.get(tl or "", "#5f5e5e")
tl_label = _TL_LABEL.get(tl or "", "Not Assessed")

# ── Hero card (nested surfaces: surface-low outer → surface-lowest inner) ─────
if any(s in status for s in ["complete", "extracted", "sufficient"]):
    status_chip = f'<span class="chip chip-green">{status.replace("_"," ")}</span>'
elif "error" in status:
    status_chip = f'<span class="chip chip-red">{status.replace("_"," ")}</span>'
else:
    status_chip = f'<span class="chip chip-blue">{status.replace("_"," ")}</span>'

# SVG gauge
rs_obj    = frd_data.get("risk_score") or {}
high_met  = rs_obj.get("high_criteria_met", 0)
med_met   = rs_obj.get("medium_criteria_met", 0)
pct_gauge = {"green": 0.25, "amber": 0.65, "red": 0.85}.get(tl or "", 0.5)
# r=58, circ≈364
gauge_offset = 364 * (1 - pct_gauge)

gauge_svg = f"""
<div style="display:flex;flex-direction:column;align-items:center;gap:0.5rem;">
  <span style="font-family:'Inter',sans-serif;font-size:0.6875rem;font-weight:700;
               text-transform:uppercase;letter-spacing:0.2em;color:#5f5e5e;">
    Credit Risk Score
  </span>
  <div style="position:relative;width:8rem;height:8rem;display:flex;
              align-items:center;justify-content:center;">
    <svg style="width:100%;height:100%;transform:rotate(-90deg);" viewBox="0 0 128 128">
      <circle cx="64" cy="64" r="58" fill="transparent"
              stroke="#eae7e7" stroke-width="8"/>
      <circle cx="64" cy="64" r="58" fill="transparent"
              stroke="{tl_color}" stroke-width="8"
              stroke-dasharray="364.4"
              stroke-dashoffset="{gauge_offset:.1f}"
              stroke-linecap="round"/>
    </svg>
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;
                align-items:center;justify-content:center;text-align:center;">
      <span style="font-family:'Manrope',sans-serif;font-size:2rem;font-weight:800;
                   color:{tl_color};line-height:1;font-variant-numeric:tabular-nums;">
        {tl.upper() if tl else "—"}
      </span>
      <span style="font-size:0.5625rem;font-weight:700;text-transform:uppercase;
                   color:{tl_color};letter-spacing:0.04em;">{tl_label}</span>
    </div>
  </div>
</div>
""".strip() if tl else """
<div style="text-align:center;padding:1.5rem;color:#5f5e5e;font-size:0.875rem;">
  Run the full pipeline to see the risk verdict.
</div>
""".strip()

st.markdown(f"""
<div style="background:#f6f3f2;border-radius:0.75rem;padding:4px;margin-bottom:2rem;">
  <div style="background:#ffffff;border-radius:0.625rem;
              box-shadow:0 8px 32px 0 rgba(28,27,27,0.06);padding:2rem 2.5rem;">
    <div style="display:flex;align-items:center;justify-content:space-between;
                gap:2rem;flex-wrap:wrap;">
      <div style="flex:1;min-width:200px;">
        <h2 style="font-family:'Manrope',sans-serif;font-size:2.25rem;font-weight:800;
                   letter-spacing:-0.03em;color:#1c1b1b;line-height:1.1;margin-bottom:0.5rem;">
          Results Overview
        </h2>
        <p style="font-family:'Inter',sans-serif;font-size:0.8125rem;font-weight:600;
                  text-transform:uppercase;letter-spacing:0.12em;color:#5f5e5e;margin-bottom:1rem;">
          Case ID: {active_case} · {ctype}
        </p>
        <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;">
          <span class="chip chip-gray">{ctype}</span>
          <span class="chip chip-gray">{sector}</span>
          {status_chip}
        </div>
      </div>
      <div style="padding:0 2rem;border-left:1px solid rgba(233,188,181,0.2);">
        {gauge_svg}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;min-width:280px;">
        <div style="background:#f6f3f2;border-radius:0.5rem;padding:1rem 1.25rem;">
          <div style="font-family:'Inter',sans-serif;font-size:0.625rem;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.12em;color:#5f5e5e;
                      margin-bottom:0.375rem;">High Criteria Met</div>
          <div style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:700;
                      color:{tl_color};font-variant-numeric:tabular-nums;">{high_met}</div>
        </div>
        <div style="background:#f6f3f2;border-radius:0.5rem;padding:1rem 1.25rem;">
          <div style="font-family:'Inter',sans-serif;font-size:0.625rem;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.12em;color:#5f5e5e;
                      margin-bottom:0.375rem;">Medium Criteria Met</div>
          <div style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:700;
                      color:#1c1b1b;font-variant-numeric:tabular-nums;">{med_met}</div>
        </div>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Two-column layout ─────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 1], gap="large")

# ── LEFT: Quantitative ────────────────────────────────────────────────────────
with left_col:
    st.markdown(_html("""
    <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem;">
      <span class="msym" style="color:#b70100;">analytics</span>
      <h3 style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:700;
                 letter-spacing:-0.02em;color:#1c1b1b;margin:0;">Quantitative Analysis</h3>
    </div>
    """), unsafe_allow_html=True)

    zs         = ff.get("current_z_score") or {}
    ratios     = ff.get("ratios") or {}
    components = zs.get("components") or {}

    # Z-Score card
    z_score   = zs.get("score")
    z_zone    = zs.get("zone", "unknown")
    z_formula = zs.get("formula_used", "")
    z_color   = {"safe": "#15803d", "grey": "#d97706", "distress": "#b70100"}.get(
        z_zone, "#5f5e5e"
    )
    zone_chip_colors = {
        "safe":     ("rgba(21,128,61,0.08)", "#15803d"),
        "grey":     ("rgba(217,119,6,0.08)", "#d97706"),
        "distress": ("rgba(183,1,0,0.08)",   "#b70100"),
    }
    zc_bg, zc_fg = zone_chip_colors.get(z_zone, ("rgba(95,94,94,0.08)", "#5f5e5e"))

    st.markdown(
        f'<div style="background:#f6f3f2;border-radius:0.5rem;padding:1.5rem;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem;">'
        f'<div>'
        f'<h4 style="font-family:\'Manrope\',sans-serif;font-size:1.0625rem;font-weight:700;color:#1c1b1b;margin-bottom:0.25rem;">Altman Z-Score Calculation</h4>'
        f'<p style="font-size:0.8125rem;color:#5f5e5e;margin:0;">Deterministic distress prediction model</p>'
        f'</div>'
        f'<span style="background:{zc_bg};color:{zc_fg};padding:0.25rem 0.625rem;border-radius:0.25rem;font-size:0.625rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;">'
        f'{z_zone.upper()} ZONE</span>'
        f'</div>',
        unsafe_allow_html=True)

    for comp_key, comp_label in [
        ("X1", "Working Capital / Total Assets"),
        ("X2", "Retained Earnings / Total Assets"),
        ("X3", "EBIT / Total Assets"),
        ("X4", "Equity / Total Liabilities"),
        ("X5", "Revenue / Total Assets"),
    ]:
        # Stored keys are verbose e.g. "X1_working_capital_to_assets"
        v = next((val for k, val in components.items() if k.startswith(comp_key)), None)
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:0.5rem 0;border-bottom:1px solid rgba(233,188,181,0.12);">'
            f'<span style="font-size:0.8125rem;color:#5f3f3a;">'
            f'<span style="font-weight:600;color:#1c1b1b;">{comp_key}</span>'
            f'&nbsp;{comp_label}</span>'
            f'<span style="font-family:\'Manrope\',sans-serif;font-variant-numeric:tabular-nums;'
            f'font-size:0.875rem;font-weight:600;color:#1c1b1b;">{_fmt(v)}</span>'
            f'</div>',
            unsafe_allow_html=True)

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:1rem 0 0.25rem;margin-top:0.5rem;">'
        f'<span style="font-family:\'Inter\',sans-serif;font-size:0.75rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.08em;color:#5f5e5e;">Final Z-Score</span>'
        f'<span style="font-family:\'Manrope\',sans-serif;font-size:2rem;font-weight:800;'
        f'color:{z_color};font-variant-numeric:tabular-nums;">{_fmt(z_score)}</span>'
        f'</div>'
        f'<div style="font-size:0.6875rem;color:#5f5e5e;padding-bottom:0.25rem;">'
        f'Formula: {z_formula.replace("_", " ").title()}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True)

    # Bento ratios
    st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)
    b1, b2 = st.columns(2, gap="small")
    for col, label, val, sub in [
        (b1, "Liquidity Ratio",  ratios.get("current_ratio"), "Current Ratio"),
        (b2, "Debt to Equity",   ratios.get("debt_to_equity"), "Leverage"),
    ]:
        with col:
            st.markdown(_html(f"""
            <div style="background:#ffffff;border-radius:0.5rem;padding:1.25rem;
                        box-shadow:0 4px 20px 0 rgba(28,27,27,0.06);
                        border:1px solid rgba(233,188,181,0.05);">
              <span style="font-size:0.625rem;font-weight:700;text-transform:uppercase;
                           letter-spacing:0.1em;color:#5f5e5e;display:block;margin-bottom:0.625rem;">
                {label}
              </span>
              <div style="font-family:'Manrope',sans-serif;font-size:1.75rem;font-weight:700;
                          color:#1c1b1b;font-variant-numeric:tabular-nums;">{_fmt(val)}</div>
              <div style="font-size:0.75rem;color:#5f5e5e;margin-top:3px;">{sub}</div>
            </div>
            """), unsafe_allow_html=True)


# ── RIGHT: Qualitative ────────────────────────────────────────────────────────
with right_col:
    st.markdown(_html("""
    <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1.25rem;">
      <span class="msym" style="color:#b70100;">neurology</span>
      <h3 style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:700;
                 letter-spacing:-0.02em;color:#1c1b1b;margin:0;">Qualitative Assessment</h3>
    </div>
    """), unsafe_allow_html=True)

    # SIS signals
    signals = sis_data.get("signals") or []
    sig_meta = sis_data.get("metadata") or {}

    st.markdown(_html("""
    <div style="background:#f6f3f2;border-radius:0.5rem;padding:1.5rem;margin-bottom:1.25rem;">
      <div style="display:flex;align-items:center;justify-content:space-between;
                  margin-bottom:1.25rem;">
        <h4 style="font-family:'Manrope',sans-serif;font-weight:700;font-size:1.0625rem;
                   color:#1c1b1b;margin:0;">LLM Analysis Highlights</h4>
        <span style="background:rgba(105,115,130,0.1);color:#697382;padding:0.25rem 0.5rem;
                     border-radius:0.25rem;font-size:0.625rem;font-weight:700;
                     text-transform:uppercase;letter-spacing:0.06em;">AI ENHANCED</span>
      </div>
    """), unsafe_allow_html=True)

    if signals:
        sev_order  = {"high": 0, "medium": 1, "low": 2, "positive": 3}
        sorted_sigs = sorted(signals,
                             key=lambda s: sev_order.get(s.get("severity", "low"), 2))

        _icon = {"high": "warning", "medium": "info", "low": "circle",
                 "positive": "gavel"}
        _border = {"high": "#b70100", "medium": "#d97706",
                   "low": "#5f5e5e", "positive": "#15803d"}
        _icon_color = {"high": "#b70100", "medium": "#d97706",
                       "low": "#5f5e5e", "positive": "#15803d"}

        for sig in sorted_sigs[:6]:
            sev      = sig.get("severity", "low")
            etype    = sig.get("event_type", "—").replace("_", " ").title()
            esubtype = sig.get("event_subtype", "").replace("_", " ")
            conf     = sig.get("confidence", 0.0)
            evidence = sig.get("evidence") or []
            snippet  = evidence[0].get("snippet", "") if evidence else ""
            icon     = _icon.get(sev, "circle")
            border   = _border.get(sev, "#5f5e5e")
            icolor   = _icon_color.get(sev, "#5f5e5e")

            sev_chip = {
                "high":     '<span class="chip chip-red">HIGH</span>',
                "medium":   '<span class="chip chip-amber">MEDIUM</span>',
                "low":      '<span class="chip chip-gray">LOW</span>',
                "positive": '<span class="chip chip-green">POSITIVE</span>',
            }.get(sev, '<span class="chip chip-gray">—</span>')

            snip_html = (
                f'<p style="font-size:0.8125rem;color:#5f3f3a;line-height:1.55;margin-top:0.375rem;">'
                f'{snippet[:200]}{"…" if len(snippet) > 200 else ""}</p>'
                if snippet else ""
            )

            st.markdown(_html(f"""
            <div style="display:flex;gap:1rem;padding:1rem;background:#ffffff;
                        border-radius:0.5rem;margin-bottom:0.75rem;
                        box-shadow:0 4px 20px 0 rgba(28,27,27,0.06);
                        border-left:4px solid {border};">
              <span class="msym" style="color:{icolor};flex-shrink:0;">{icon}</span>
              <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;justify-content:space-between;
                            gap:0.5rem;margin-bottom:0.25rem;">
                  <span style="font-family:'Manrope',sans-serif;font-size:0.875rem;
                               font-weight:700;color:#1c1b1b;">{etype}</span>
                  {sev_chip}
                </div>
                {"" if not esubtype else f'<p style="font-size:0.75rem;color:#5f5e5e;margin:0 0 2px;">{esubtype}</p>'}
                {snip_html}
              </div>
            </div>
            """), unsafe_allow_html=True)

        if sig_meta:
            total  = sig_meta.get("signals_extracted", len(signals))
            auto_v = sig_meta.get("signals_auto_verified", 0)
            st.markdown(_html(f"""
            <p style="font-size:0.75rem;color:#5f5e5e;margin:0.5rem 0 0;">
              {total} signals extracted · {auto_v} auto-verified
            </p>
            """), unsafe_allow_html=True)
    else:
        st.markdown(_html("""
        <div style="color:#5f5e5e;font-size:0.875rem;padding:1rem 0;">
          No signals extracted. Run SIS to extract risk signals.
        </div>
        """), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # RS coverage / market sentiment
    coverage = case_data.get("coverage") or {}
    covered  = coverage.get("topics_covered") or []
    missing  = coverage.get("topics_missing") or []

    if covered or missing:
        total_topics = len(covered) + len(missing)
        cov_pct = len(covered) / total_topics if total_topics else 0

        st.markdown(_html(f"""
        <div style="background:#f6f3f2;border-radius:0.5rem;padding:1.5rem;">
          <h4 style="font-family:'Manrope',sans-serif;font-weight:700;font-size:1.0625rem;
                     color:#1c1b1b;margin-bottom:1.25rem;">Market Sentiment Analysis</h4>
          <div style="margin-bottom:0.625rem;display:flex;justify-content:space-between;">
            <span style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                         color:#5f5e5e;letter-spacing:0.06em;">Coverage</span>
            <span style="font-size:0.75rem;font-weight:700;color:#5f5e5e;">
              {int(cov_pct * 100)}%
            </span>
          </div>
          <div style="height:6px;background:#eae7e7;border-radius:9999px;overflow:hidden;
                      margin-bottom:0.75rem;">
            <div style="height:100%;width:{int(cov_pct*100)}%;background:#15803d;
                        border-radius:9999px;"></div>
          </div>
          <p style="font-size:0.8125rem;font-style:italic;color:#5f3f3a;margin:0;">
            {len(covered)} of {total_topics} topics covered in external retrieval.
          </p>
        </div>
        """), unsafe_allow_html=True)

# ── FRD Report ────────────────────────────────────────────────────────────────
if frd_data:
    st.markdown("<div class='atelier-hr'></div>", unsafe_allow_html=True)
    st.markdown(_html("""
    <div class="section-label">
      <div class="section-label-bar"></div>
      <div class="section-label-text">Risk Decisioning Report</div>
    </div>
    """), unsafe_allow_html=True)

    rs_obj   = frd_data.get("risk_score") or {}
    criteria = rs_obj.get("criteria_results") or []
    flags    = rs_obj.get("flags") or []
    mit      = rs_obj.get("mitigating_details") or []

    if criteria:
        with st.expander("Risk criteria breakdown", expanded=True):
            for cr in criteria:
                met = cr.get("met", False)
                met_chip = (
                    '<span class="chip chip-red">Met</span>'
                    if met else
                    '<span class="chip chip-green">Not met</span>'
                )
                weight  = cr.get("weight", "").upper()
                w_chip  = f'<span class="chip chip-gray">{weight}</span>'
                st.markdown(_html(f"""
                <div style="display:flex;align-items:flex-start;gap:0.75rem;
                            padding:0.625rem 0;
                            border-bottom:1px solid rgba(233,188,181,0.12);">
                  <div style="flex:1;">
                    <div style="font-size:0.875rem;font-weight:600;color:#1c1b1b;">
                      {cr.get('criteria_name','—')}
                    </div>
                    <div style="font-size:0.75rem;color:#5f5e5e;margin-top:3px;">
                      {cr.get('detail','')[:220]}
                    </div>
                  </div>
                  <div style="display:flex;gap:0.375rem;flex-shrink:0;">
                    {w_chip}{met_chip}
                  </div>
                </div>
                """), unsafe_allow_html=True)

    if flags:
        with st.expander("Risk flags"):
            for f in flags:
                st.markdown(
                    f'<div style="font-size:0.875rem;color:#b70100;padding:3px 0;">▸ {f}</div>',
                    unsafe_allow_html=True)

    if mit:
        with st.expander("Mitigating factors"):
            for m in mit:
                st.markdown(
                    f'<div style="font-size:0.875rem;color:#15803d;padding:3px 0;">✓ {m}</div>',
                    unsafe_allow_html=True)

    report = frd_data.get("report_narrative") or (frd_data.get("report") or {}).get("full_narrative")
    if report:
        with st.expander("Full analyst report narrative"):
            st.markdown(report)

# ── Downloads ─────────────────────────────────────────────────────────────────
st.markdown("<div class='atelier-hr'></div>", unsafe_allow_html=True)
dl1, dl2, _ = st.columns([2, 2, 6], gap="small")
with dl1:
    st.download_button(
        "Download result (JSON)",
        data=json.dumps(case_data, indent=2, default=str),
        file_name=f"{active_case}_result.json",
        mime="application/json",
        use_container_width=True,
    )
with dl2:
    report = frd_data.get("report_narrative") or (frd_data.get("report") or {}).get("full_narrative")
    if report:
        st.download_button(
            "Download report narrative",
            data=report,
            file_name=f"{active_case}_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

# ── AI Chat Assistant ─────────────────────────────────────────────────────────
st.markdown("<div class='atelier-hr'></div>", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;">
  <span class="material-symbols-outlined" style="color:#b70100;">auto_awesome</span>
  <div class="section-label-text">Credit Intelligence Assistant</div>
  <span class="chip chip-green" style="font-size:0.5625rem;margin-left:auto;">ONLINE</span>
</div>
<p style="font-size:0.8125rem;color:#5f5e5e;margin-bottom:0.75rem;">
  Ask questions about this case — the assistant has full context of the financial
  data, signals, and risk findings.
</p>
""", unsafe_allow_html=True)

_chat_key = f"chat_history_{active_case}"
if _chat_key not in st.session_state:
    st.session_state[_chat_key] = []
chat_history = st.session_state[_chat_key]

# Quick actions
qa_cols = st.columns([2, 2, 2, 4], gap="small")
quick_actions = [
    ("Analyze Z-Score",    "Explain the Altman Z-Score result and what it means for this company's financial health."),
    ("ESG Implications",   "What are the ESG and ethical risk implications from the analysis?"),
    ("Market Pulse",       "Summarize the market sentiment and key signals identified for this company."),
]
st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
for col, (label, prompt) in zip(qa_cols[:3], quick_actions):
    with col:
        if st.button(label, use_container_width=True):
            chat_history.append({"role": "user", "content": prompt})
            try:
                resp = requests.post(
                    f"{api_base}/api/cases/{active_case}/chat",
                    json={"message": prompt, "history": chat_history[:-1]},
                    timeout=60,
                )
                reply = resp.json().get("reply", "No response.") if resp.status_code == 200 \
                    else f"Error {resp.status_code}: {resp.text[:200]}"
            except requests.ConnectionError:
                reply = "Cannot connect to API."
            except Exception as exc:
                reply = str(exc)
            chat_history.append({"role": "assistant", "content": reply})
            st.session_state[_chat_key] = chat_history
            st.rerun()

# Chat history
for msg in chat_history:
    role = msg["role"]
    content = msg["content"]
    if role == "user":
        avatar_html = (
            '<div style="width:2rem;height:2rem;border-radius:9999px;background:#e2dfde;'
            'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
            '<svg xmlns="http://www.w3.org/2000/svg" height="18" viewBox="0 96 960 960" width="18" fill="#5f5e5e">'
            '<path d="M480 575q-66 0-108-42t-42-108q0-66 42-108t108-42q66 0 108 42t42 108q0 66-42 108t-108 42ZM160 896v-94q0-38 19-65t49-41q67-30 130.5-45T480 636q69 0 132 15t130 45q30 14 49 41t19 65v94H160Z"/>'
            '</svg></div>'
        )
        align = "flex-end"
        bubble_bg = "#f6f3f2"
        margin = "margin-left:3rem;"
    else:
        avatar_html = (
            '<div style="width:2rem;height:2rem;border-radius:9999px;background:#b70100;'
            'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
            '<svg xmlns="http://www.w3.org/2000/svg" height="18" viewBox="0 96 960 960" width="18" fill="#ffffff">'
            '<path d="M160 816v-460q0-24 18-42t42-18h520q24 0 42 18t18 42v320q0 24-18 42t-42 18H240L160 816Zm260-195h40v-80h80v-40h-80v-80h-40v80h-80v40h80v80Z"/>'
            '</svg></div>'
        )
        align = "flex-start"
        bubble_bg = "#ffffff"
        margin = "margin-right:3rem;"

    st.markdown(
        f'<div style="display:flex;align-items:flex-start;gap:0.75rem;'
        f'margin-bottom:0.75rem;flex-direction:{"row-reverse" if role == "user" else "row"};">'
        f'{avatar_html}'
        f'<div style="background:{bubble_bg};border-radius:0.625rem;padding:0.75rem 1rem;'
        f'{margin}font-size:0.9375rem;line-height:1.6;color:#1c1b1b;'
        f'border:1px solid rgba(233,188,181,0.15);box-shadow:0 2px 8px rgba(28,27,27,0.04);">'
        f'{content}</div></div>',
        unsafe_allow_html=True,
    )

# Chat input — use text_area + form so it stays inline (st.chat_input pins to viewport bottom)
with st.form("chat_form", clear_on_submit=True):
    user_msg = st.text_area(
        "Your question",
        placeholder="Ask a question about the analysis results…",
        label_visibility="collapsed",
        height=80,
    )
    send = st.form_submit_button("Send  →", type="primary")

if send and user_msg and user_msg.strip():
    msg = user_msg.strip()
    chat_history.append({"role": "user", "content": msg})
    with st.spinner("Thinking…"):
        try:
            resp = requests.post(
                f"{api_base}/api/cases/{active_case}/chat",
                json={"message": msg, "history": chat_history[:-1]},
                timeout=60,
            )
            reply = resp.json().get("reply", "No response.") if resp.status_code == 200 \
                else f"Error {resp.status_code}: {resp.text[:200]}"
        except requests.ConnectionError:
            reply = "Cannot connect to API. Make sure the backend is running."
        except Exception as exc:
            reply = str(exc)
    chat_history.append({"role": "assistant", "content": reply})
    st.session_state[_chat_key] = chat_history
    st.rerun()
