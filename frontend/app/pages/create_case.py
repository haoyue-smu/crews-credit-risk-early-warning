"""Create Case page."""

import requests

api_base = st.session_state.get("api_base", "http://localhost:8000")

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <div>
        <h1>Create Case</h1>
        <p>Register a company for credit risk assessment</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Intake form ───────────────────────────────────────────────────────────────
with st.form("create_case_form"):
    st.markdown('<p class="section-label" style="margin-top: 0;">Company details</p>', unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        company_name = st.text_input(
            "Company name *",
            placeholder="e.g. Acme Manufacturing Corp",
        )
        company_type = st.selectbox(
            "Company type *",
            ["private", "public"],
            help="Public companies use the original Altman Z-Score (requires market cap).",
        )
        industry_sector = st.selectbox(
            "Industry sector",
            [
                "",
                "manufacturing", "technology", "healthcare", "retail",
                "real_estate", "energy", "utilities", "consumer_goods",
                "telecommunications", "financial_services", "transportation",
                "media_entertainment",
            ],
        )
        is_manufacturing = st.checkbox(
            "Primary manufacturing company",
            help="Enables the manufacturing variant of the Altman Z-Score.",
        )

    with col2:
        jurisdiction = st.text_input("Jurisdiction", placeholder="e.g. US, UK, SG")
        ticker = st.text_input("Ticker symbol", placeholder="e.g. AAPL")
        isin = st.text_input("ISIN", placeholder="Optional")
        website = st.text_input("Website", placeholder="https://example.com")
        market_cap = st.number_input(
            "Market cap (USD)",
            min_value=0.0,
            value=0.0,
            help="Required for public companies — used in the original Z-Score.",
        )

    submitted = st.form_submit_button(
        "Create case",
        use_container_width=True,
        type="primary",
    )

if submitted:
    if not company_name.strip():
        st.error("Company name is required.")
    else:
        payload = {
            "company_name": company_name.strip(),
            "company_type": company_type,
            "jurisdiction": jurisdiction or None,
            "ticker": ticker or None,
            "isin": isin or None,
            "website": website or None,
            "industry_sector": industry_sector or None,
            "is_manufacturing": is_manufacturing,
            "market_cap": market_cap if market_cap > 0 else None,
        }
        try:
            resp = requests.post(f"{api_base}/api/cases", json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                case_id = data["case_id"]
                st.session_state["active_case_id"] = case_id
                st.markdown(f"""
                <div style="background: #E6F4EA; border-radius: 8px; padding: 16px 20px;
                            display: flex; align-items: center; gap: 12px; margin-top: 8px;">
                    <span style="font-size: 20px;">✓</span>
                    <div>
                        <div style="font-size: 14px; font-weight: 500; color: #137333;">
                            Case created successfully
                        </div>
                        <div style="font-size: 12px; font-family: 'Roboto Mono', monospace;
                                    color: #137333; margin-top: 2px;">{case_id}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.caption("Navigate to **Upload Documents** to attach financial statements.")
            else:
                st.error(f"API error {resp.status_code}: {resp.text}")
        except requests.ConnectionError:
            st.error("Cannot connect to the API. Make sure the backend is running.")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

# ── Existing cases ────────────────────────────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.markdown('<p class="section-label">Existing cases</p>', unsafe_allow_html=True)

try:
    resp = requests.get(f"{api_base}/api/cases", timeout=5)
    if resp.status_code == 200:
        cases = resp.json()
        if not cases:
            st.markdown("""
            <div class="empty-state">
                <div class="es-icon">📋</div>
                <div class="es-title">No cases yet</div>
                <div class="es-body">Create a case above to get started.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for c in cases:
                status = c["status"]
                if any(s in status for s in ["complete", "extracted", "sufficient"]):
                    chip = '<span class="chip chip-green">complete</span>'
                elif "error" in status:
                    chip = f'<span class="chip chip-red">{status}</span>'
                elif "running" in status or status == "created":
                    chip = f'<span class="chip chip-blue">{status}</span>'
                else:
                    chip = f'<span class="chip chip-gray">{status}</span>'

                is_active = st.session_state.get("active_case_id") == c["case_id"]
                border = "border: 1px solid #1A73E8;" if is_active else "border: 1px solid #DADCE0;"

                col_main, col_btn = st.columns([10, 1])
                with col_main:
                    st.markdown(f"""
                    <div class="card" style="margin-bottom: 8px; {border}">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div>
                                <div style="font-size: 14px; font-weight: 500; color: #202124;">
                                    {c['company_name']}
                                </div>
                                <div style="font-size: 11px; font-family: 'Roboto Mono', monospace;
                                            color: #5F6368; margin-top: 3px;">{c['case_id']}</div>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                {chip}
                                {"<span style='font-size: 11px; color: #1A73E8; font-weight: 500;'>● active</span>" if is_active else ""}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_btn:
                    if st.button("Select", key=f"sel_{c['case_id']}", use_container_width=True):
                        st.session_state["active_case_id"] = c["case_id"]
                        st.rerun()

except requests.ConnectionError:
    st.warning("Backend not reachable. Start the API server and refresh.")
except Exception:
    pass
