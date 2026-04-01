"""Results page — full analysis output."""

import json
import requests
import pandas as pd

api_base    = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

# ── Guard ─────────────────────────────────────────────────────────────────────
if not active_case:
    st.markdown("""
    <div class="empty-state" style="margin-top: 60px;">
        <div class="es-icon">📊</div>
        <div class="es-title">No active case</div>
        <div class="es-body">Go to <strong>Create Case</strong> and select a case first.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Fetch data ────────────────────────────────────────────────────────────────
try:
    resp = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=10)
    if resp.status_code != 200:
        st.error(f"Could not load case ({resp.status_code}).")
        st.stop()
    case_data = resp.json()
except requests.ConnectionError:
    st.error("Cannot connect to API.")
    st.stop()
except Exception as exc:
    st.error(f"Error: {exc}")
    st.stop()

company = case_data.get("company", {})
ff      = case_data.get("financial_features")
status  = case_data.get("status", "unknown")

# ── Page header ───────────────────────────────────────────────────────────────
if any(s in status for s in ["complete", "extracted", "sufficient"]):
    status_chip = f'<span class="chip chip-green">{status}</span>'
elif "error" in status:
    status_chip = f'<span class="chip chip-red">{status}</span>'
elif "running" in status:
    status_chip = f'<span class="chip chip-blue">{status}</span>'
else:
    status_chip = f'<span class="chip chip-gray">{status}</span>'

st.markdown(f"""
<div class="page-header">
    <div>
        <h1>{company.get('company_name', active_case)}</h1>
        <p>
            {company.get('company_type', '').upper()}
            {('&nbsp;·&nbsp;' + company.get('industry_sector', '').replace('_', ' ').title()) if company.get('industry_sector') else ''}
            {('&nbsp;·&nbsp;' + company.get('jurisdiction', '')) if company.get('jurisdiction') else ''}
        </p>
    </div>
    <div style="display: flex; align-items: center; gap: 8px;">
        {status_chip}
    </div>
</div>
""", unsafe_allow_html=True)

# ── Traffic light hero (if FRD complete) ─────────────────────────────────────
frd_output = case_data.get("frd_output")
if frd_output:
    traffic_light = frd_output.get("traffic_light", "unknown")
    _TL = {
        "green": ("tl-green", "●", "GREEN",  "Low credit risk"),
        "amber": ("tl-amber", "●", "AMBER",  "Medium credit risk — review required"),
        "red":   ("tl-red",   "●", "RED",    "High credit risk — escalate for review"),
    }
    css, icon, label, subtitle = _TL.get(traffic_light, ("tl-gray", "○", "UNKNOWN", "FRD not complete"))

    st.markdown(f"""
    <div class="tl-hero {css}">
        <div class="tl-icon">{icon}</div>
        <div class="tl-verdict">{label}</div>
        <div class="tl-sub">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

# ── No financial features yet ─────────────────────────────────────────────────
if not ff:
    st.markdown("""
    <div class="card" style="text-align: center; padding: 40px;">
        <div style="font-size: 14px; color: #5F6368;">
            Financial features are not available yet. Run <strong>FIS</strong> to compute them.
        </div>
    </div>
    """, unsafe_allow_html=True)

    audit_log = case_data.get("audit_log", [])
    if audit_log:
        with st.expander(f"Audit log — {len(audit_log)} events"):
            _df = pd.DataFrame([{
                "Time":   ae.get("timestamp", "")[:19],
                "Node":   ae.get("node_name", ""),
                "Event":  ae.get("event", ""),
            } for ae in audit_log])
            st.dataframe(_df, use_container_width=True, hide_index=True)
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_fin, tab_zscore, tab_signals, tab_frd, tab_retrieval, tab_audit = st.tabs([
    "Financials", "Z-Score", "Signals", "FRD Report", "Retrieval", "Audit",
])

# ── Tab: Financials ───────────────────────────────────────────────────────────
with tab_fin:
    # Key ratios overview
    ratios = ff.get("ratios", {}) or {}
    ratio_items = {k: v for k, v in ratios.items() if v is not None and k != "computation_notes"}

    if ratio_items:
        st.markdown('<p class="section-label" style="margin-top: 8px;">Key ratios</p>', unsafe_allow_html=True)

        groups = {
            "Liquidity":    ["current_ratio", "quick_ratio", "cash_ratio"],
            "Leverage":     ["debt_to_equity", "debt_to_assets", "net_debt_to_ebitda", "interest_coverage"],
            "Profitability":["gross_margin", "operating_margin", "net_margin", "ebitda_margin",
                             "return_on_assets", "return_on_equity"],
            "Efficiency":   ["asset_turnover"],
        }

        col1, col2 = st.columns(2, gap="large")
        for col, (group_name, keys) in zip([col1, col2, col1, col2], groups.items()):
            items = {k: ratio_items[k] for k in keys if k in ratio_items}
            if not items:
                continue
            with col:
                st.markdown(f"**{group_name}**")
                rcols = st.columns(min(len(items), 3))
                for rcol, (k, v) in zip(rcols, items.items()):
                    label = k.replace("_", " ").title()
                    if any(x in k for x in ["margin", "return_on"]):
                        rcol.metric(label, f"{v*100:.1f}%")
                    else:
                        rcol.metric(label, f"{v:.3f}")

        notes = ratios.get("computation_notes", [])
        if notes:
            with st.expander("Computation notes"):
                for n in notes:
                    st.caption(f"⚠ {n}")

    # Financial statements
    st.markdown('<p class="section-label">Statements</p>', unsafe_allow_html=True)
    stab_is, stab_bs, stab_cf = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])

    def _fmt_value(v):
        if isinstance(v, float) and abs(v) >= 100:
            return f"${v:,.0f}"
        if isinstance(v, int) and abs(v) >= 100:
            return f"${v:,}"
        return str(v)

    with stab_is:
        items = {k: v for k, v in (ff.get("income_statement") or {}).items() if v is not None}
        if items:
            df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": _fmt_value(v)}
                                for k, v in items.items()])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No income statement data.")

    with stab_bs:
        items = {k: v for k, v in (ff.get("balance_sheet") or {}).items() if v is not None}
        if items:
            df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": _fmt_value(v)}
                                for k, v in items.items()])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No balance sheet data.")

    with stab_cf:
        items = {k: v for k, v in (ff.get("cash_flow") or {}).items() if v is not None}
        if items:
            df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": _fmt_value(v)}
                                for k, v in items.items()])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No cash flow data.")

# ── Tab: Z-Score ──────────────────────────────────────────────────────────────
with tab_zscore:
    z = ff.get("current_z_score")
    if z and z.get("score") is not None:
        score   = z["score"]
        zone    = z.get("zone", "unknown")
        formula = z.get("formula_used", "unknown")

        zone_css  = {"safe": "zone-safe", "grey": "zone-grey", "distress": "zone-distress"}.get(zone, "")
        zone_label = zone.upper() + " ZONE"

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Altman Z-Score", f"{score:.4f}")
        with c2:
            st.markdown(f"""
            <div style="padding: 16px 0 8px;">
                <div style="font-size: 12px; color: #5F6368; margin-bottom: 6px;">Zone</div>
                <span class="{zone_css}">{zone_label}</span>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.metric("Formula", formula.replace("_", " ").title())

        # Thresholds
        thresholds = z.get("zone_thresholds", {})
        if thresholds:
            safe_t = thresholds.get("safe", "—")
            dist_t = thresholds.get("distress", "—")
            st.markdown(f"""
            <div style="background: #F8F9FA; border-radius: 8px; padding: 12px 16px;
                        font-size: 12px; color: #5F6368; margin: 8px 0;">
                <span class="zone-safe">Safe ≥ {safe_t}</span>&ensp;
                <span class="zone-grey">Grey zone</span>&ensp;
                <span class="zone-distress">Distress &lt; {dist_t}</span>
            </div>
            """, unsafe_allow_html=True)

        # Components
        components = z.get("components", {})
        if components:
            with st.expander("Z-Score components"):
                cdf = pd.DataFrame(
                    [{"Component": k.upper(), "Value": round(v, 6)}
                     for k, v in components.items() if v is not None]
                )
                st.dataframe(cdf, use_container_width=True, hide_index=True)

        # Peer comparison
        peer = ff.get("peer_comparison")
        if peer:
            with st.expander(f"Peer comparison — {peer.get('industry_sector', 'N/A')}"):
                pc1, pc2, pc3 = st.columns(3)
                median = peer.get("industry_median_z")
                if median is not None:
                    pc1.metric("Industry median Z", f"{median:.2f}", delta=f"{score - median:+.2f}")
                else:
                    pc1.metric("Industry median Z", "N/A")
                safe_pct = peer.get("industry_safe_zone_pct")
                pc2.metric("Industry safe zone %", f"{safe_pct*100:.0f}%" if safe_pct else "N/A")
                dist_pct = peer.get("industry_distress_zone_pct")
                pc3.metric("Industry distress zone %", f"{dist_pct*100:.0f}%" if dist_pct else "N/A")
                for note in (peer.get("notes") or []):
                    st.caption(note)

        # Historical Z-Scores
        hist_z = ff.get("historical_z_scores", [])
        if hist_z:
            with st.expander(f"Historical Z-Scores — {len(hist_z)} periods"):
                hdf = pd.DataFrame([{
                    "Period": hz.get("period_label", "?"),
                    "Score":  round(hz["score"], 4) if hz.get("score") is not None else None,
                    "Zone":   hz.get("zone", "").upper(),
                } for hz in hist_z if hz.get("score") is not None])
                if not hdf.empty:
                    st.dataframe(hdf, use_container_width=True, hide_index=True)
    else:
        st.info("Z-Score not computed. Check warnings in the Audit tab.")

# ── Tab: Signals ──────────────────────────────────────────────────────────────
with tab_signals:
    sis_output = case_data.get("sis_output")
    if not sis_output:
        st.markdown("""
        <div class="empty-state" style="padding: 40px;">
            <div class="es-icon">🧠</div>
            <div class="es-title">No signal data</div>
            <div class="es-body">Run <strong>SIS</strong> to extract risk signals from retrieved documents.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        signals = sis_output.get("signals", [])
        meta    = sis_output.get("metadata", {}) or {}

        # Metadata row
        if meta:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Docs processed",    meta.get("docs_processed", "—"))
            mc2.metric("Signals extracted", meta.get("signals_extracted", len(signals)))
            mc3.metric("Auto-verified",     meta.get("auto_verified", "—"))
            mc4.metric("Ambiguous",         meta.get("ambiguous_count", "—"))

        if signals:
            _SEV_CHIP = {
                "high":     '<span class="chip chip-red">HIGH</span>',
                "medium":   '<span class="chip chip-yellow">MED</span>',
                "low":      '<span class="chip chip-gray">LOW</span>',
                "positive": '<span class="chip chip-green">POS</span>',
            }

            rows = []
            for s in signals:
                rows.append({
                    "Severity":  s.get("severity", "—"),
                    "Type":      s.get("event_type", "—"),
                    "Subtype":   s.get("event_subtype", "—"),
                    "Confidence": f"{s.get('confidence', 0):.0%}" if s.get("confidence") is not None else "—",
                    "Conflict":  s.get("conflict_status", "—"),
                    "Ambiguous": "Yes" if s.get("ambiguous") else "No",
                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

            with st.expander("Signal evidence details"):
                for i, s in enumerate(signals[:15]):
                    sev   = s.get("severity", "?").upper()
                    etype = s.get("event_type", "?")
                    esub  = s.get("event_subtype", "?")
                    st.markdown(f"**{i+1}. [{sev}] {etype} / {esub}**")
                    for ev in (s.get("evidence") or [])[:2]:
                        if isinstance(ev, dict):
                            snippet = ev.get("snippet") or ev.get("text", "")
                            src     = ev.get("source_name", "")
                            st.markdown(f"> {str(snippet)[:300]}")
                            if src:
                                st.caption(f"Source: {src}")
                    st.markdown('<div style="height: 1px; background: #F1F3F4; margin: 8px 0;"></div>',
                                unsafe_allow_html=True)
        else:
            st.caption("No signals extracted.")

# ── Tab: FRD Report ───────────────────────────────────────────────────────────
with tab_frd:
    if not frd_output:
        st.markdown("""
        <div class="empty-state" style="padding: 40px;">
            <div class="es-icon">⚖️</div>
            <div class="es-title">No FRD output</div>
            <div class="es-body">Run <strong>FRD</strong> after SIS completes.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        risk_score = frd_output.get("risk_score", {}) or {}
        criteria   = risk_score.get("criteria_results", [])

        if criteria:
            st.markdown('<p class="section-label" style="margin-top: 8px;">Criteria scorecard</p>',
                        unsafe_allow_html=True)

            crit_rows = []
            for c in criteria:
                crit_rows.append({
                    "Weight":   c.get("weight", "—").upper(),
                    "Criteria": c.get("criteria_name", "—"),
                    "Met":      "Yes" if c.get("met") else "No",
                    "Signals":  c.get("contributing_signal_count", 0),
                    "Detail":   (c.get("detail") or "")[:90],
                })
            st.dataframe(
                pd.DataFrame(crit_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Met": st.column_config.TextColumn(width="small"),
                    "Signals": st.column_config.NumberColumn(width="small"),
                },
            )

            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("High criteria met",   risk_score.get("high_criteria_met", 0))
            fc2.metric("Medium criteria met", risk_score.get("medium_criteria_met", 0))
            fc3.metric("Low criteria met",    risk_score.get("low_criteria_met", 0))

        flags = risk_score.get("flags", [])
        if flags:
            st.markdown('<p class="section-label">Flags</p>', unsafe_allow_html=True)
            for flag in flags:
                st.warning(flag)

        mitigating = risk_score.get("mitigating_details", [])
        if mitigating:
            with st.expander("Mitigating factors"):
                for m in mitigating:
                    st.success(m)

        # Analyst narrative
        report = frd_output.get("report_narrative") or (frd_output.get("report") or {}).get("full_narrative")
        if report:
            st.markdown('<p class="section-label">Analyst report</p>', unsafe_allow_html=True)
            with st.expander("View full narrative", expanded=True):
                st.markdown(report)

# ── Tab: Retrieval ────────────────────────────────────────────────────────────
with tab_retrieval:
    retrieval = case_data.get("raw_retrieval_results", [])
    coverage  = case_data.get("coverage", {}) or {}

    if not retrieval:
        st.markdown("""
        <div class="empty-state" style="padding: 40px;">
            <div class="es-icon">🔍</div>
            <div class="es-title">No retrieval results</div>
            <div class="es-body">Run <strong>RS</strong> to search external sources.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        if coverage:
            cov_status = coverage.get("status", "unknown")
            chip_css   = "chip-green" if cov_status == "sufficient" else "chip-yellow"
            covered    = coverage.get("topics_covered", [])
            missing    = coverage.get("topics_missing", [])

            st.markdown(f"""
            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
                        padding: 12px 16px; background: #F8F9FA; border-radius: 8px;
                        border: 1px solid #E8EAED; margin-bottom: 16px;">
                <span class="chip {chip_css}">{cov_status}</span>
                <span style="font-size: 12px; color: #5F6368;">
                    {coverage.get('attempts', 0)} attempt{"s" if coverage.get('attempts', 0) != 1 else ""}
                </span>
                {'<span style="font-size: 12px; color: #137333;">Covered: ' + ', '.join(covered) + '</span>' if covered else ''}
                {'<span style="font-size: 12px; color: #B06000;">Missing: ' + ', '.join(missing) + '</span>' if missing else ''}
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f'<p class="section-label">{len(retrieval)} items</p>', unsafe_allow_html=True)

        with st.expander("View retrieved items", expanded=False):
            for item in retrieval[:25]:
                quality = item.get("raw_payload", {}).get("_quality_score")
                q_str   = f"{quality:.2f}" if quality is not None else "—"
                source  = item.get("source", "?")
                title   = item.get("title") or "Untitled"
                url     = item.get("url", "#")
                snippet = (item.get("snippet") or "")[:160]

                st.markdown(f"""
                <div style="padding: 10px 0; border-bottom: 1px solid #F1F3F4;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span class="chip chip-gray">{source}</span>
                        <a href="{url}" target="_blank" style="font-size: 13px; font-weight: 500;
                           color: #1A73E8; text-decoration: none;">{title}</a>
                        <span style="font-size: 11px; color: #9AA0A6; margin-left: auto;">q={q_str}</span>
                    </div>
                    <div style="font-size: 12px; color: #5F6368; line-height: 1.4;">{snippet}</div>
                </div>
                """, unsafe_allow_html=True)

# ── Tab: Audit ────────────────────────────────────────────────────────────────
with tab_audit:
    audit_log = case_data.get("audit_log", [])
    warnings  = case_data.get("warnings", [])
    errors    = case_data.get("errors", [])
    ff_warns  = (ff or {}).get("warnings", [])

    if warnings or errors or ff_warns:
        st.markdown('<p class="section-label" style="margin-top: 8px;">Warnings & errors</p>',
                    unsafe_allow_html=True)
        for w in warnings + ff_warns:
            st.warning(w)
        for e in errors:
            st.error(e)

    if audit_log:
        st.markdown(f'<p class="section-label">{len(audit_log)} audit events</p>', unsafe_allow_html=True)
        adf = pd.DataFrame([{
            "Time":    ae.get("timestamp", "")[:19],
            "Node":    ae.get("node_name", ""),
            "Event":   ae.get("event", ""),
            "Details": str(ae.get("details", {}))[:100],
        } for ae in audit_log])
        st.dataframe(adf, use_container_width=True, hide_index=True)
    else:
        st.caption("No audit events recorded yet.")

# ── Downloads ─────────────────────────────────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
dl1, dl2 = st.columns(2)
with dl1:
    st.download_button(
        "Download full JSON",
        data=json.dumps(case_data, indent=2, default=str),
        file_name=f"{active_case}_result.json",
        mime="application/json",
        use_container_width=True,
    )
with dl2:
    if ff:
        st.download_button(
            "Download financial features",
            data=json.dumps(ff, indent=2, default=str),
            file_name=f"{active_case}_financials.json",
            mime="application/json",
            use_container_width=True,
        )
