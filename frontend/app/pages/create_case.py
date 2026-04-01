"""Create Case page — Company intake form."""

import requests

st.markdown("### 📋 Create New Case")
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

with st.form("create_case_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        company_name = st.text_input("Company Name *", placeholder="e.g. Acme Manufacturing Corp")
        company_type = st.selectbox("Company Type *", ["private", "public"])
        industry_sector = st.selectbox("Industry Sector", [
            "", "manufacturing", "technology", "healthcare", "retail",
            "real_estate", "energy", "utilities", "consumer_goods",
            "telecommunications", "financial_services", "transportation",
            "media_entertainment",
        ])
        is_manufacturing = st.checkbox("Manufacturing Company", help="Select if the company is primarily in manufacturing (affects Z-Score formula)")
    
    with col2:
        jurisdiction = st.text_input("Jurisdiction", placeholder="e.g. US, UK, SG")
        ticker = st.text_input("Ticker Symbol", placeholder="e.g. AAPL (for public companies)")
        isin = st.text_input("ISIN", placeholder="Optional")
        website = st.text_input("Website", placeholder="e.g. https://acme.com")
        market_cap = st.number_input("Market Cap (USD)", min_value=0.0, value=0.0, 
                                      help="Required for public companies (Original Z-Score)")
    
    submitted = st.form_submit_button("🚀 Create Case", use_container_width=True, type="primary")

if submitted:
    if not company_name:
        st.error("Company name is required.")
    else:
        api_base = st.session_state.get("api_base", "http://localhost:8000")
        try:
            payload = {
                "company_name": company_name,
                "company_type": company_type,
                "jurisdiction": jurisdiction or None,
                "ticker": ticker or None,
                "isin": isin or None,
                "website": website or None,
                "industry_sector": industry_sector or None,
                "is_manufacturing": is_manufacturing,
                "market_cap": market_cap if market_cap > 0 else None,
            }
            resp = requests.post(f"{api_base}/api/cases", json=payload, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"✅ Case created: **{data['case_id']}**")
                st.session_state["active_case_id"] = data["case_id"]
                st.json(data)
            else:
                st.error(f"API error: {resp.status_code} — {resp.text}")
        except requests.ConnectionError:
            st.error("❌ Cannot connect to API. Is the backend running on the configured URL?")
        except Exception as e:
            st.error(f"Error: {e}")

# Show existing cases
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### Existing Cases")

api_base = st.session_state.get("api_base", "http://localhost:8000")
try:
    resp = requests.get(f"{api_base}/api/cases", timeout=5)
    if resp.status_code == 200:
        cases = resp.json()
        if cases:
            for c in cases:
                status_class = "status-complete" if "complete" in c["status"] or "extracted" in c["status"] else "status-running"
                if "error" in c["status"]:
                    status_class = "status-error"
                
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    st.markdown(f"**{c['company_name']}**")
                with col2:
                    st.code(c["case_id"])
                with col3:
                    st.markdown(f'<span class="status-badge {status_class}">{c["status"]}</span>', unsafe_allow_html=True)
                with col4:
                    if st.button("Select", key=f"sel_{c['case_id']}"):
                        st.session_state["active_case_id"] = c["case_id"]
                        st.rerun()
        else:
            st.info("No cases yet. Create one above.")
except requests.ConnectionError:
    st.warning("Backend not connected. Start the API server first.")
except Exception:
    pass
