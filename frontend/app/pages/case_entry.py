"""Case Entry page — new case intake and document upload."""

import requests

api_base    = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-breadcrumb">
  <span>Credit Assessment</span>
  <span style="margin:0 0.25rem;color:#5f5e5e;">›</span>
  <span class="bc-active">New Case Intake</span>
</div>
<div class="page-heading">Initialize Credit Review</div>
<div class="page-subheading">
  Begin a new counterparty risk assessment by providing the entity's core details
  and supporting documentation for our analytical engine.
</div>
""", unsafe_allow_html=True)

# ── Entity Details — form is styled as white card via [data-testid="stForm"] CSS ──
with st.form("case_entry_form"):
    st.markdown("""
    <div class="section-label">
      <div class="section-label-bar"></div>
      <div class="section-label-text">Entity Details</div>
    </div>
    """, unsafe_allow_html=True)

    company_name = st.text_input(
        "COMPANY NAME",
        placeholder="Enter legal entity name...",
    )

    col1, col2 = st.columns(2, gap="large")
    with col1:
        company_type = st.text_input(
            "ENTITY TYPE",
            placeholder="e.g. private or public",
        )
    with col2:
        industry_sector = st.text_input(
            "INDUSTRY SECTOR",
            placeholder="e.g. technology, healthcare, retail...",
        )

    jurisdiction = st.text_input(
        "JURISDICTION OF OPERATION",
        placeholder="Enter primary jurisdiction (e.g. United States)",
    )

    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    col_cta, col_note = st.columns([3, 5])
    with col_cta:
        submitted = st.form_submit_button(
            "Initialize Assessment  →",
            use_container_width=True,
            type="primary",
        )
    with col_note:
        st.markdown(
            "<p style='font-size:0.75rem;color:#5f5e5e;padding-top:0.625rem;"
            "font-family:\"Inter\",sans-serif;line-height:1.5;'>"
            "Data is encrypted and stored in accordance with UBS Global Compliance"
            " standards for Institutional Data Handling."
            "</p>",
            unsafe_allow_html=True,
        )

if submitted:
    if not company_name.strip():
        st.error("Company name is required.")
    else:
        payload = {
            "company_name": company_name.strip(),
            "company_type": company_type,
            "industry_sector": industry_sector or None,
            "jurisdiction": jurisdiction.strip() or None,
        }
        try:
            resp = requests.post(f"{api_base}/api/cases", json=payload, timeout=10)
            if resp.status_code == 200:
                case_id = resp.json()["case_id"]
                st.session_state["active_case_id"] = case_id
                st.markdown(f"""
                <div style="background:rgba(21,128,61,0.07);border-radius:0.625rem;
                            padding:1rem 1.25rem;margin-top:0.75rem;display:flex;
                            align-items:center;gap:0.875rem;">
                  <span class="material-symbols-outlined" style="color:#15803d;font-size:1.5rem;">check_circle</span>
                  <div>
                    <div style="font-family:'Manrope',sans-serif;font-size:0.9375rem;
                                font-weight:700;color:#15803d;">Case created successfully</div>
                    <div style="font-size:0.75rem;font-family:'Courier New',monospace;
                                color:#15803d;margin-top:3px;">{case_id}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                st.caption("Scroll down to upload supporting financial documents.")
            else:
                st.error(f"API error {resp.status_code}: {resp.text}")
        except requests.ConnectionError:
            st.error("Cannot connect to the API. Make sure the backend is running.")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

# ── Supporting Documents ──────────────────────────────────────────────────────
st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:1rem;flex-wrap:wrap;gap:0.75rem;">
      <div>
        <div class="section-label" style="margin-bottom:0.375rem;">
          <div class="section-label-bar"></div>
          <div class="section-label-text">Supporting Documents</div>
        </div>
        <p style="font-size:0.875rem;color:#5f5e5e;margin:0;line-height:1.55;">
          Upload 10-K, registration proofs, and recent balance sheets.
        </p>
      </div>
      <div style="display:flex;gap:0.375rem;flex-wrap:wrap;">
        <span class="chip chip-primary">PDF</span>
        <span class="chip chip-primary">XML</span>
        <span class="chip chip-primary">XBRL</span>
        <span class="chip chip-gray">Max 50 MB</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not active_case and not st.session_state.get("active_case_id"):
        st.info("Create or select a case above before uploading documents.")
    else:
        current_case = st.session_state.get("active_case_id")

        col_up, col_role = st.columns([3, 1], gap="medium")
        with col_up:
            uploaded_files = st.file_uploader(
                "Drag and drop financial files here",
                type=["xml", "xbrl", "pdf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
        with col_role:
            document_role = st.text_input(
                "DOCUMENT ROLE",
                placeholder="e.g. annual_report, quarterly_report",
                value="annual_report",
            )

        if uploaded_files:
            for uf in uploaded_files:
                ext     = uf.name.rsplit(".", 1)[-1].upper() if "." in uf.name else "FILE"
                size_kb = round(len(uf.getvalue()) / 1024, 1)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:0.875rem;
                            padding:0.75rem 1rem;background:#ffffff;
                            border-radius:0.5rem;margin-bottom:0.375rem;
                            box-shadow:0 2px 8px rgba(28,27,27,0.04);">
                  <span class="material-symbols-outlined" style="color:#b70100;">description</span>
                  <div style="flex:1;min-width:0;">
                    <div style="font-size:0.875rem;font-weight:600;color:#1c1b1b;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                      {uf.name}
                    </div>
                    <div style="font-size:0.6875rem;color:#5f5e5e;margin-top:1px;">
                      {size_kb} KB · Ready to process
                    </div>
                  </div>
                  <span class="chip chip-blue">{ext}</span>
                </div>
                """, unsafe_allow_html=True)

            if st.button("Upload documents", type="primary"):
                ok, errs = [], []
                for uf in uploaded_files:
                    try:
                        r = requests.post(
                            f"{api_base}/api/cases/{current_case}/documents",
                            files={"file": (uf.name, uf.getvalue(), "application/octet-stream")},
                            data={"document_role": document_role},
                            timeout=30,
                        )
                        if r.status_code == 200:
                            ok.append((uf.name, r.json().get("document_id", "")))
                        else:
                            errs.append((uf.name, r.text))
                    except requests.ConnectionError:
                        errs.append((uf.name, "Cannot connect to API"))
                    except Exception as exc:
                        errs.append((uf.name, str(exc)))

                if ok:
                    st.markdown(f"""
                    <div style="background:rgba(21,128,61,0.07);border-radius:0.625rem;
                                padding:0.875rem 1.25rem;margin-top:0.5rem;">
                      <div style="font-family:'Manrope',sans-serif;font-size:0.9375rem;
                                  font-weight:700;color:#15803d;margin-bottom:0.375rem;">
                        {len(ok)} file{'s' if len(ok) > 1 else ''} uploaded successfully
                      </div>
                    """, unsafe_allow_html=True)
                    for fname, doc_id in ok:
                        st.markdown(f"""
                      <div style="font-size:0.75rem;color:#15803d;padding:1px 0;">
                        {fname}
                        <span style="font-family:'Courier New',monospace;margin-left:6px;opacity:0.7;">
                          → {doc_id}
                        </span>
                      </div>
                        """, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                for fname, msg in errs:
                    st.error(f"{fname}: {msg}")

        # Uploaded documents list
        st.markdown('<div class="atelier-hr"></div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="section-label">
          <div class="section-label-bar"></div>
          <div class="section-label-text">Uploaded Documents</div>
        </div>
        """, unsafe_allow_html=True)

        try:
            r = requests.get(f"{api_base}/api/cases/{current_case}/result", timeout=5)
            if r.status_code == 200:
                docs = r.json().get("uploaded_financial_documents", [])
                if not docs:
                    st.markdown("""
                    <div style="padding:1.5rem;text-align:center;color:#5f5e5e;font-size:0.875rem;">
                      No documents uploaded yet.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    for doc in docs:
                        ext    = doc.get("file_type", "?").upper()
                        role   = doc.get("document_role", "—").replace("_", " ").title()
                        doc_id = doc.get("document_id", "")[:16] + "…"
                        st.markdown(f"""
                        <div style="display:flex;align-items:center;gap:0.75rem;
                                    padding:0.625rem 0.875rem;background:#ffffff;
                                    border-radius:0.5rem;margin-bottom:0.375rem;
                                    box-shadow:0 2px 8px rgba(28,27,27,0.04);">
                          <span class="chip chip-blue" style="font-size:0.625rem;">{ext}</span>
                          <span style="flex:1;font-size:0.875rem;font-weight:500;color:#1c1b1b;">
                            {doc['filename']}
                          </span>
                          <span style="font-size:0.75rem;color:#5f5e5e;">{role}</span>
                          <span style="font-size:0.6875rem;color:#5f5e5e;
                                       font-family:'Courier New',monospace;">{doc_id}</span>
                        </div>
                        """, unsafe_allow_html=True)
        except Exception:
            pass

# ── Existing Cases ────────────────────────────────────────────────────────────
st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
st.markdown("""
<div class="section-label">
  <div class="section-label-bar"></div>
  <div class="section-label-text">Existing Cases</div>
</div>
""", unsafe_allow_html=True)

try:
    r = requests.get(f"{api_base}/api/cases", timeout=5)
    if r.status_code == 200:
        cases = r.json()
        if not cases:
            st.markdown("""
            <div style="padding:2rem;text-align:center;color:#5f5e5e;font-size:0.875rem;">
              No cases yet. Create one above.
            </div>
            """, unsafe_allow_html=True)
        else:
            for c in cases:
                s         = c["status"]
                is_active = st.session_state.get("active_case_id") == c["case_id"]

                if any(x in s for x in ["complete", "extracted", "sufficient"]):
                    chip = f'<span class="chip chip-green">{s}</span>'
                elif "error" in s:
                    chip = f'<span class="chip chip-red">{s}</span>'
                elif "running" in s:
                    chip = f'<span class="chip chip-blue">{s}</span>'
                else:
                    chip = f'<span class="chip chip-gray">{s}</span>'

                active_badge = (
                    '<span class="chip chip-primary" style="margin-left:0.25rem;font-size:0.5625rem;">active</span>'
                    if is_active else ""
                )
                border = "border-left:3px solid #b70100;" if is_active else "border-left:3px solid transparent;"

                col_info, col_btn = st.columns([10, 1])
                with col_info:
                    st.markdown(f"""
                    <div style="background:#ffffff;border-radius:0.75rem;margin-bottom:0.5rem;
                                {border}padding:0.875rem 1.25rem;
                                box-shadow:0 4px 16px rgba(28,27,27,0.05);">
                      <div style="display:flex;align-items:center;
                                  justify-content:space-between;gap:0.75rem;">
                        <div style="min-width:0;">
                          <div style="font-family:'Manrope',sans-serif;font-size:0.9375rem;
                                      font-weight:600;color:#1c1b1b;">{c['company_name']}</div>
                          <div style="font-size:0.6875rem;font-family:'Courier New',monospace;
                                      color:#5f5e5e;margin-top:2px;">{c['case_id']}</div>
                        </div>
                        <div style="display:flex;align-items:center;gap:0.375rem;flex-shrink:0;">
                          {chip}{active_badge}
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
