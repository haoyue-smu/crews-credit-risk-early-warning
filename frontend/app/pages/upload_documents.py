"""Upload Documents page — File uploader for financial documents."""

import requests

st.markdown("### 📄 Upload Financial Documents")
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

api_base = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

if not active_case:
    st.warning("⚠️ No active case selected. Go to **Create Case** first, or select an existing case.")
    st.stop()

st.info(f"📎 Active Case: **{active_case}**")

# File upload
uploaded_files = st.file_uploader(
    "Upload financial documents (XML, XBRL, or PDF)",
    type=["xml", "xbrl", "pdf"],
    accept_multiple_files=True,
    help="Upload annual or quarterly reports in XML, XBRL, or PDF format."
)

if uploaded_files:
    document_role = st.selectbox("Document Role", ["annual_report", "quarterly_report"])
    
    if st.button("📤 Upload All Files", type="primary", use_container_width=True):
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
                    st.success(f"✅ Uploaded **{uf.name}** → Document ID: `{result['document_id']}`")
                else:
                    st.error(f"❌ Failed to upload {uf.name}: {resp.text}")
            except requests.ConnectionError:
                st.error("Cannot connect to API.")
            except Exception as e:
                st.error(f"Error uploading {uf.name}: {e}")

# Show current case documents
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown("### Uploaded Documents")

try:
    resp = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=5)
    if resp.status_code == 200:
        case_data = resp.json()
        docs = case_data.get("uploaded_financial_documents", [])
        if docs:
            for doc in docs:
                col1, col2, col3 = st.columns([4, 2, 2])
                with col1:
                    st.markdown(f"📄 **{doc['filename']}**")
                with col2:
                    st.code(doc['file_type'].upper())
                with col3:
                    st.caption(doc.get("document_role", "—"))
        else:
            st.info("No documents uploaded yet.")
    else:
        st.warning("Could not load case data.")
except requests.ConnectionError:
    st.warning("Backend not connected.")
except Exception:
    pass
