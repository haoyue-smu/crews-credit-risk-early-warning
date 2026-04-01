"""Run Analysis page — Execute FIS/RS with live status polling."""

import time
import requests

st.markdown("### 🚀 Run Analysis")
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

api_base = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

if not active_case:
    st.warning("⚠️ No active case selected. Go to **Create Case** first.")
    st.stop()

st.info(f"🔬 Active Case: **{active_case}**")

# Current status
try:
    resp = requests.get(f"{api_base}/api/cases/{active_case}/status", timeout=5)
    if resp.status_code == 200:
        status_data = resp.json()
        current_status = status_data["status"]
        
        status_class = "status-running"
        if any(s in current_status for s in ["complete", "extracted", "sufficient"]):
            status_class = "status-complete"
        elif "error" in current_status:
            status_class = "status-error"
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Current Status</h3>
                <div><span class="status-badge {status_class}">{current_status}</span></div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Audit Events</h3>
                <div class="value">{status_data['audit_log_count']}</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            warning_count = len(status_data.get("warnings", []))
            error_count = len(status_data.get("errors", []))
            st.markdown(f"""
            <div class="metric-card">
                <h3>Warnings / Errors</h3>
                <div class="value">{warning_count} / {error_count}</div>
            </div>
            """, unsafe_allow_html=True)
except Exception:
    st.warning("Could not fetch status.")

st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

# Action buttons
col1, col2, col3 = st.columns(3)

with col1:
    run_fis = st.button("📑 Run FIS Only", use_container_width=True, 
                         help="Financial Ingestion — parse documents, compute ratios & Z-Score")

with col2:
    run_rs = st.button("🔍 Run RS Only", use_container_width=True,
                        help="Retrieval Subgraph — search external sources")

with col3:
    run_all = st.button("⚡ Run Full Pipeline", use_container_width=True, type="primary",
                         help="FIS → RS sequentially")

# Trigger actions
triggered_action = None
if run_fis:
    triggered_action = ("run-fis", "FIS")
elif run_rs:
    triggered_action = ("run-rs", "RS")
elif run_all:
    triggered_action = ("run-all", "Full Pipeline")

if triggered_action:
    endpoint, label = triggered_action
    try:
        resp = requests.post(f"{api_base}/api/cases/{active_case}/{endpoint}", timeout=10)
        if resp.status_code == 200:
            st.success(f"🚀 {label} started!")
            
            # Live polling
            progress_bar = st.progress(0, text=f"Running {label}...")
            status_container = st.empty()
            
            for i in range(60):  # Poll for up to 60 seconds
                time.sleep(2)
                try:
                    poll = requests.get(f"{api_base}/api/cases/{active_case}/status", timeout=5)
                    if poll.status_code == 200:
                        poll_data = poll.json()
                        current = poll_data["status"]
                        
                        progress = min((i + 1) / 30, 0.95)
                        
                        # Check if done
                        is_done = any(s in current for s in [
                            "fis_features_extracted", "rs_complete", 
                            "fis_error", "rs_error",
                            "rs_coverage_sufficient", "rs_coverage_exhausted",
                        ])
                        
                        if is_done:
                            progress = 1.0
                        
                        progress_bar.progress(progress, text=f"Status: {current}")
                        status_container.markdown(f"**Status:** `{current}` | **Audit events:** {poll_data['audit_log_count']}")
                        
                        if is_done:
                            if "error" in current:
                                st.error(f"❌ {label} failed: {current}")
                                if poll_data.get("errors"):
                                    for err in poll_data["errors"]:
                                        st.error(err)
                            else:
                                st.success(f"✅ {label} completed: {current}")
                            break
                except Exception:
                    pass
            else:
                st.warning("⏰ Polling timeout. Check the Results page for final status.")
                
        else:
            st.error(f"Failed to start: {resp.text}")
    except requests.ConnectionError:
        st.error("Cannot connect to API.")
    except Exception as e:
        st.error(f"Error: {e}")
