"""Upload Documents page."""

import requests

api_base = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

# ── Guard ─────────────────────────────────────────────────────────────────────
if not active_case:
    st.markdown("""
    <div class="empty-state" style="margin-top: 60px;">
        <div class="es-icon">📄</div>
        <div class="es-title">No active case</div>
        <div class="es-body">Go to <strong>Create Case</strong> to create or select a case first.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="page-header">
    <div>
        <h1>Upload Documents</h1>
        <p>Attach financial statements for <span class="mono">{active_case}</span></p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Uploader ──────────────────────────────────────────────────────────────────
st.markdown('<p class="section-label" style="margin-top: 0;">Select files</p>', unsafe_allow_html=True)

col_up, col_role = st.columns([3, 1], gap="medium")

with col_up:
    uploaded_files = st.file_uploader(
        "XML, XBRL, or PDF",
        type=["xml", "xbrl", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

with col_role:
    document_role = st.selectbox(
        "Document role",
        ["annual_report", "quarterly_report"],
    )

if uploaded_files:
    # Preview selected files
    st.markdown(f"""
    <div style="background: #F8F9FA; border-radius: 8px; padding: 12px 16px; margin: 8px 0 16px;">
        <div style="font-size: 12px; font-weight: 500; color: #5F6368; margin-bottom: 8px;">
            {len(uploaded_files)} file{"s" if len(uploaded_files) > 1 else ""} selected
        </div>
    """, unsafe_allow_html=True)

    for uf in uploaded_files:
        ext = uf.name.rsplit(".", 1)[-1].upper() if "." in uf.name else "FILE"
        size_kb = round(len(uf.getvalue()) / 1024, 1)
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 10px; padding: 6px 0;
                    border-bottom: 1px solid #E8EAED;">
            <span style="font-size: 11px; font-weight: 700; color: #1967D2;
                         background: #E8F0FE; padding: 2px 6px; border-radius: 4px;">{ext}</span>
            <span style="font-size: 13px; color: #202124; flex: 1;">{uf.name}</span>
            <span style="font-size: 11px; color: #9AA0A6;">{size_kb} KB</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Upload files", type="primary", use_container_width=False):
        upload_results = []
        for uf in uploaded_files:
            try:
                files = {"file": (uf.name, uf.getvalue(), "application/octet-stream")}
                data = {"document_role": document_role}
                resp = requests.post(
                    f"{api_base}/api/cases/{active_case}/documents",
                    files=files,
                    data=data,
                    timeout=30,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    upload_results.append(("ok", uf.name, result.get("document_id", "")))
                else:
                    upload_results.append(("err", uf.name, resp.text))
            except requests.ConnectionError:
                upload_results.append(("err", uf.name, "Cannot connect to API"))
            except Exception as exc:
                upload_results.append(("err", uf.name, str(exc)))

        ok = [r for r in upload_results if r[0] == "ok"]
        err = [r for r in upload_results if r[0] == "err"]

        if ok:
            st.markdown(f"""
            <div style="background: #E6F4EA; border-radius: 8px; padding: 14px 18px; margin-top: 12px;">
                <div style="font-size: 13px; font-weight: 500; color: #137333; margin-bottom: 6px;">
                    {len(ok)} file{"s" if len(ok) > 1 else ""} uploaded successfully
                </div>
            """, unsafe_allow_html=True)
            for _, fname, doc_id in ok:
                st.markdown(f"""
                <div style="font-size: 12px; color: #137333; padding: 2px 0;">
                    {fname}
                    <span style="font-family: 'Roboto Mono', monospace; margin-left: 8px;">→ {doc_id}</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        for _, fname, msg in err:
            st.error(f"{fname}: {msg}")

# ── Current documents ─────────────────────────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.markdown('<p class="section-label">Uploaded documents</p>', unsafe_allow_html=True)

try:
    resp = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=5)
    if resp.status_code == 200:
        docs = resp.json().get("uploaded_financial_documents", [])
        if not docs:
            st.markdown("""
            <div class="empty-state" style="padding: 32px;">
                <div class="es-icon" style="font-size: 28px;">📂</div>
                <div class="es-title">No documents yet</div>
                <div class="es-body">Upload files above to get started.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="card">
                <div style="font-size: 11px; font-weight: 500; color: #5F6368;
                            letter-spacing: 0.6px; text-transform: uppercase; margin-bottom: 12px;">
                    {len(docs)} document{"s" if len(docs) > 1 else ""}
                </div>
            """, unsafe_allow_html=True)

            for doc in docs:
                ext = doc.get("file_type", "?").upper()
                role = doc.get("document_role", "—").replace("_", " ").title()
                doc_id = doc.get("document_id", "")[:16] + "…"
                st.markdown(f"""
                <div class="doc-row">
                    <span style="font-size: 11px; font-weight: 700; color: #1967D2;
                                 background: #E8F0FE; padding: 2px 7px; border-radius: 4px;
                                 flex-shrink: 0;">{ext}</span>
                    <span style="font-size: 13px; color: #202124; flex: 1; font-weight: 500;">
                        {doc['filename']}
                    </span>
                    <span style="font-size: 11px; color: #5F6368;">{role}</span>
                    <span style="font-size: 10px; font-family: 'Roboto Mono', monospace;
                                 color: #9AA0A6;">{doc_id}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("Could not load case data.")
except requests.ConnectionError:
    st.warning("Backend not reachable.")
except Exception:
    pass
