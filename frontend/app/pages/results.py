"""Results page — Financial features, Z-Score, ratios, audit log."""

import json
import requests
import pandas as pd

st.markdown("### 📊 Analysis Results")
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

api_base = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

if not active_case:
    st.warning("⚠️ No active case selected.")
    st.stop()

st.info(f"📊 Viewing: **{active_case}**")

# Fetch full results
try:
    resp = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=10)
    if resp.status_code != 200:
        st.error(f"Could not load case: {resp.status_code}")
        st.stop()
    case_data = resp.json()
except requests.ConnectionError:
    st.error("Cannot connect to API.")
    st.stop()
except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

# ---- Summary Header ----
company = case_data.get("company", {})
ff = case_data.get("financial_features")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Company</h3>
        <div class="value" style="font-size: 1.2rem;">{company.get('company_name', 'N/A')}</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Type</h3>
        <div class="value">{company.get('company_type', 'N/A').upper()}</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Industry</h3>
        <div class="value" style="font-size: 1rem;">{company.get('industry_sector', 'N/A')}</div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    status = case_data.get("status", "unknown")
    status_class = "status-complete" if any(s in status for s in ["extracted", "complete", "sufficient"]) else "status-running"
    if "error" in status:
        status_class = "status-error"
    st.markdown(f"""
    <div class="metric-card">
        <h3>Status</h3>
        <div><span class="status-badge {status_class}">{status}</span></div>
    </div>
    """, unsafe_allow_html=True)

if not ff:
    st.info("Financial features not yet available. Run FIS first.")
    # Still show audit log if available
    audit_log = case_data.get("audit_log", [])
    if audit_log:
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        _show_audit = st.expander(f"📋 Audit Log ({len(audit_log)} events)", expanded=False)
        with _show_audit:
            for ae in audit_log:
                st.markdown(f"**{ae.get('node_name')}** → `{ae.get('event')}` _{ae.get('timestamp', '')}_")
    st.stop()

# ---- Z-Score Section ----
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### 🎯 Altman Z-Score")

z_score = ff.get("current_z_score")
if z_score and z_score.get("score") is not None:
    score = z_score["score"]
    zone = z_score.get("zone", "unknown")
    formula = z_score.get("formula_used", "unknown")
    thresholds = z_score.get("zone_thresholds", {})
    
    zone_class = f"zone-{zone}"
    zone_emoji = {"safe": "🟢", "grey": "🟡", "distress": "🔴"}.get(zone, "⚪")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Z-Score</h3>
            <div class="value">{score:.4f}</div>
            <div><span class="{zone_class}">{zone_emoji} {zone.upper()} ZONE</span></div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Formula</h3>
            <div class="value" style="font-size: 1rem;">{formula.replace('_', ' ').title()}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        safe_t = thresholds.get("safe", "—")
        dist_t = thresholds.get("distress", "—")
        st.markdown(f"""
        <div class="metric-card">
            <h3>Thresholds</h3>
            <div style="font-size: 0.9rem;">
                <span class="zone-safe">Safe ≥ {safe_t}</span>&nbsp;
                <span class="zone-distress">Distress &lt; {dist_t}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Z-Score components
    components = z_score.get("components", {})
    if components:
        with st.expander("Z-Score Components", expanded=False):
            comp_data = {k: [v] for k, v in components.items() if v is not None}
            if comp_data:
                st.dataframe(pd.DataFrame(comp_data).T.rename(columns={0: "Value"}), use_container_width=True)
    
    # Peer comparison
    peer = ff.get("peer_comparison")
    if peer:
        with st.expander(f"📊 Peer Comparison — {peer.get('industry_sector', 'N/A')}", expanded=False):
            pcol1, pcol2, pcol3 = st.columns(3)
            with pcol1:
                median = peer.get("industry_median_z")
                if median is not None:
                    delta = score - median
                    st.metric("Industry Median Z", f"{median:.2f}", delta=f"{delta:+.2f}")
                else:
                    st.metric("Industry Median Z", "N/A")
            with pcol2:
                safe_pct = peer.get("industry_safe_zone_pct")
                st.metric("Safe Zone %", f"{safe_pct*100:.0f}%" if safe_pct else "N/A")
            with pcol3:
                dist_pct = peer.get("industry_distress_zone_pct")
                st.metric("Distress Zone %", f"{dist_pct*100:.0f}%" if dist_pct else "N/A")
            if peer.get("notes"):
                for note in peer["notes"]:
                    st.caption(f"ℹ️ {note}")
    
    # Historical Z-Scores
    hist_z = ff.get("historical_z_scores", [])
    if hist_z:
        with st.expander(f"📈 Historical Z-Scores ({len(hist_z)} periods)", expanded=False):
            hist_df = pd.DataFrame([
                {
                    "Period": hz.get("period_label", "?"),
                    "Score": hz.get("score"),
                    "Zone": hz.get("zone", "unknown").upper(),
                }
                for hz in hist_z if hz.get("score") is not None
            ])
            if not hist_df.empty:
                st.dataframe(hist_df, use_container_width=True, hide_index=True)

else:
    st.info("Z-Score not computed. Check warnings below.")

# ---- Financial Ratios ----
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### 📐 Financial Ratios")

ratios = ff.get("ratios", {})
ratio_items = {k: v for k, v in ratios.items() if v is not None and k != "computation_notes"}

if ratio_items:
    # Group ratios
    liquidity = {k: v for k, v in ratio_items.items() if k in ["current_ratio", "quick_ratio", "cash_ratio"]}
    leverage = {k: v for k, v in ratio_items.items() if k in ["debt_to_equity", "debt_to_assets", "net_debt_to_ebitda", "interest_coverage"]}
    profitability = {k: v for k, v in ratio_items.items() if k in ["gross_margin", "operating_margin", "net_margin", "ebitda_margin", "return_on_assets", "return_on_equity"]}
    efficiency = {k: v for k, v in ratio_items.items() if k in ["asset_turnover"]}
    
    col1, col2 = st.columns(2)
    with col1:
        if liquidity:
            st.markdown("**💧 Liquidity**")
            for k, v in liquidity.items():
                st.metric(k.replace("_", " ").title(), f"{v:.3f}")
        if leverage:
            st.markdown("**⚖️ Leverage**")
            for k, v in leverage.items():
                st.metric(k.replace("_", " ").title(), f"{v:.3f}")
    with col2:
        if profitability:
            st.markdown("**💰 Profitability**")
            for k, v in profitability.items():
                label = k.replace("_", " ").title()
                if "margin" in k or "return" in k:
                    st.metric(label, f"{v*100:.1f}%")
                else:
                    st.metric(label, f"{v:.3f}")
        if efficiency:
            st.markdown("**⚙️ Efficiency**")
            for k, v in efficiency.items():
                st.metric(k.replace("_", " ").title(), f"{v:.3f}")
    
    notes = ratios.get("computation_notes", [])
    if notes:
        with st.expander("Ratio Computation Notes"):
            for n in notes:
                st.caption(f"⚠️ {n}")
else:
    st.info("No ratios computed yet.")

# ---- Financial Statements ----
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### 📑 Financial Statement Metrics")

tab_is, tab_bs, tab_cf = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])

with tab_is:
    is_data = ff.get("income_statement", {})
    is_items = {k: v for k, v in is_data.items() if v is not None}
    if is_items:
        df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": f"${v:,.0f}" if isinstance(v, (int, float)) and v > 100 else str(v)} for k, v in is_items.items()])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No income statement data.")

with tab_bs:
    bs_data = ff.get("balance_sheet", {})
    bs_items = {k: v for k, v in bs_data.items() if v is not None}
    if bs_items:
        df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": f"${v:,.0f}" if isinstance(v, (int, float)) and abs(v) > 100 else str(v)} for k, v in bs_items.items()])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No balance sheet data.")

with tab_cf:
    cf_data = ff.get("cash_flow", {})
    cf_items = {k: v for k, v in cf_data.items() if v is not None}
    if cf_items:
        df = pd.DataFrame([{"Metric": k.replace("_", " ").title(), "Value": f"${v:,.0f}" if isinstance(v, (int, float)) and abs(v) > 100 else str(v)} for k, v in cf_items.items()])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No cash flow data.")

# ---- Retrieval Results ----
retrieval = case_data.get("raw_retrieval_results", [])
if retrieval:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(f"### 🔍 Retrieval Results ({len(retrieval)} items)")
    
    coverage = case_data.get("coverage", {})
    if coverage:
        cov_col1, cov_col2 = st.columns(2)
        with cov_col1:
            st.markdown(f"**Coverage Status:** `{coverage.get('status', 'unknown')}`")
            st.markdown(f"**Attempts:** {coverage.get('attempts', 0)}")
        with cov_col2:
            covered = coverage.get("topics_covered", [])
            missing = coverage.get("topics_missing", [])
            if covered:
                st.markdown(f"**Covered:** {', '.join(covered)}")
            if missing:
                st.markdown(f"**Missing:** {', '.join(missing)}")
    
    with st.expander("📰 Retrieved Items", expanded=False):
        for item in retrieval[:20]:
            quality = item.get("raw_payload", {}).get("_quality_score", "—")
            st.markdown(f"**[{item.get('source', '?')}]** [{item.get('title', 'No title')}]({item.get('url', '#')})")
            st.caption(f"Quality: {quality} | {(item.get('snippet', '') or '')[:150]}...")
            st.markdown("---")

# ---- Audit Log ----
audit_log = case_data.get("audit_log", [])
if audit_log:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    with st.expander(f"📋 Audit Log ({len(audit_log)} events)", expanded=False):
        audit_df = pd.DataFrame([
            {
                "Time": ae.get("timestamp", "")[:19],
                "Node": ae.get("node_name", ""),
                "Event": ae.get("event", ""),
                "Details": str(ae.get("details", {}))[:100],
            }
            for ae in audit_log
        ])
        st.dataframe(audit_df, use_container_width=True, hide_index=True)

# ---- Warnings & Errors ----
warnings = case_data.get("warnings", [])
errors = case_data.get("errors", [])
ff_warnings = ff.get("warnings", []) if ff else []

if warnings or errors or ff_warnings:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("### ⚠️ Warnings & Errors")
    for w in warnings + ff_warnings:
        st.warning(w)
    for e in errors:
        st.error(e)

# ---- Raw JSON Download ----
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(case_data, indent=2, default=str),
        file_name=f"{active_case}_result.json",
        mime="application/json",
        use_container_width=True,
    )
with col2:
    if ff:
        st.download_button(
            "📥 Download Financial Features",
            data=json.dumps(ff, indent=2, default=str),
            file_name=f"{active_case}_financial_features.json",
            mime="application/json",
            use_container_width=True,
        )
