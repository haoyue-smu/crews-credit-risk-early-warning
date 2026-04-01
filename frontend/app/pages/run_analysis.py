"""Run Analysis page — pipeline execution and live status."""

import time
import requests

api_base = st.session_state.get("api_base", "http://localhost:8000")
active_case = st.session_state.get("active_case_id")

# ── Guard ─────────────────────────────────────────────────────────────────────
if not active_case:
    st.markdown("""
    <div class="empty-state" style="margin-top: 60px;">
        <div class="es-icon">⚡</div>
        <div class="es-title">No active case</div>
        <div class="es-body">Go to <strong>Create Case</strong> to create or select a case first.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Fetch current status ───────────────────────────────────────────────────────
status_data = None
current_status = "unknown"

try:
    r = requests.get(f"{api_base}/api/cases/{active_case}/status", timeout=5)
    if r.status_code == 200:
        status_data = r.json()
        current_status = status_data.get("status", "unknown")
except Exception:
    pass

# ── Page header ───────────────────────────────────────────────────────────────
tl = (status_data or {}).get("frd_traffic_light")
_TL_CHIP = {
    "green": '<span class="chip chip-green">Green</span>',
    "amber": '<span class="chip chip-yellow">Amber</span>',
    "red":   '<span class="chip chip-red">Red</span>',
}
tl_html = _TL_CHIP.get(tl, "") if tl else ""

st.markdown(f"""
<div class="page-header">
    <div>
        <h1>Run Analysis</h1>
        <p>Execute pipeline stages for <span class="mono">{active_case}</span></p>
    </div>
    <div>{tl_html}</div>
</div>
""", unsafe_allow_html=True)

# ── Pipeline stage status cards ───────────────────────────────────────────────

def _stage_css(status: str, stage_prefix: str) -> str:
    """Return CSS modifier class based on pipeline status string."""
    if any(f"{stage_prefix}_error" in status for _ in [1]):
        return "s-error"
    if any(s in status for s in [
        f"{stage_prefix}_complete", f"{stage_prefix}_features_extracted",
        f"{stage_prefix}_coverage_sufficient", f"{stage_prefix}_coverage_exhausted",
        f"{stage_prefix}_skipped",
    ]):
        return "s-complete"
    if f"{stage_prefix}_" in status and "running" in status:
        return "s-running"
    return ""

def _stage_status_chip(status: str, stage_prefix: str) -> str:
    css = _stage_css(status, stage_prefix)
    if css == "s-complete":
        return '<span class="chip chip-green">Done</span>'
    if css == "s-running":
        return '<span class="chip chip-blue">Running</span>'
    if css == "s-error":
        return '<span class="chip chip-red">Error</span>'
    return '<span class="chip chip-gray">Pending</span>'

_STAGES = [
    ("fis", "FIS", "Financial Ingestion",
     "Parse documents, compute ratios and Altman Z-Score."),
    ("rs",  "RS",  "External Retrieval",
     "Search news, filings, and social media for signals."),
    ("sis", "SIS", "Signal Intelligence",
     "Extract, verify, and de-conflict risk signals."),
    ("frd", "FRD", "Risk Decisioning",
     "Produce traffic-light verdict and analyst report."),
]

st.markdown('<p class="section-label" style="margin-top: 0;">Pipeline status</p>', unsafe_allow_html=True)
cols = st.columns(4, gap="small")

for col, (prefix, abbr, name, desc) in zip(cols, _STAGES):
    css_mod = _stage_css(current_status, prefix)
    chip = _stage_status_chip(current_status, prefix)
    with col:
        st.markdown(f"""
        <div class="stage-card {css_mod}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                <div style="font-size: 11px; font-weight: 700; letter-spacing: 1px; color: #1A73E8;">{abbr}</div>
                {chip}
            </div>
            <div class="s-name">{name}</div>
            <div class="s-desc" style="margin-top: 4px;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

# ── Status summary bar ────────────────────────────────────────────────────────
if status_data:
    audit_count = status_data.get("audit_log_count", 0)
    warn_count  = len(status_data.get("warnings", []))
    err_count   = len(status_data.get("errors", []))

    if any(s in current_status for s in ["complete", "extracted", "sufficient"]):
        status_chip = f'<span class="chip chip-green">{current_status}</span>'
    elif "error" in current_status:
        status_chip = f'<span class="chip chip-red">{current_status}</span>'
    elif "running" in current_status:
        status_chip = f'<span class="chip chip-blue">{current_status}</span>'
    else:
        status_chip = f'<span class="chip chip-gray">{current_status}</span>'

    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 24px; padding: 14px 20px;
                background: #F8F9FA; border-radius: 8px; margin: 16px 0 24px;
                border: 1px solid #E8EAED; flex-wrap: wrap;">
        <div>
            <div style="font-size: 10px; font-weight: 500; color: #5F6368;
                        letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 3px;">Status</div>
            {status_chip}
        </div>
        <div>
            <div style="font-size: 10px; font-weight: 500; color: #5F6368;
                        letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 3px;">Audit events</div>
            <div style="font-size: 20px; font-weight: 300; color: #202124;">{audit_count}</div>
        </div>
        <div>
            <div style="font-size: 10px; font-weight: 500; color: #5F6368;
                        letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 3px;">Warnings</div>
            <div style="font-size: 20px; font-weight: 300; color: {'#B06000' if warn_count else '#202124'};">{warn_count}</div>
        </div>
        <div>
            <div style="font-size: 10px; font-weight: 500; color: #5F6368;
                        letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 3px;">Errors</div>
            <div style="font-size: 20px; font-weight: 300; color: {'#C5221F' if err_count else '#202124'};">{err_count}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Show errors inline if any
    for err in status_data.get("errors", []):
        st.error(err)

# ── Action buttons ────────────────────────────────────────────────────────────
st.markdown('<p class="section-label">Run stages</p>', unsafe_allow_html=True)

btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4, gap="small")
with btn_col1:
    run_fis = st.button("Run FIS", use_container_width=True,
                        help="Parse documents, compute Z-Score and ratios.")
with btn_col2:
    run_rs = st.button("Run RS", use_container_width=True,
                       help="Search external sources for credit signals.")
with btn_col3:
    run_sis = st.button("Run SIS", use_container_width=True,
                        help="Extract and verify risk signals.")
with btn_col4:
    run_frd = st.button("Run FRD", use_container_width=True,
                        help="Produce traffic-light verdict.")

st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)
run_all = st.button(
    "Run full pipeline  —  FIS → RS → SIS → FRD",
    use_container_width=True,
    type="primary",
)

# ── Dispatch ──────────────────────────────────────────────────────────────────
triggered = None
if run_fis:  triggered = ("run-fis",  "FIS")
elif run_rs:  triggered = ("run-rs",   "RS")
elif run_sis: triggered = ("run-sis",  "SIS")
elif run_frd: triggered = ("run-frd",  "FRD")
elif run_all: triggered = ("run-all",  "Full pipeline")

_TERMINAL = {
    "fis_features_extracted", "fis_ingestion_skipped",
    "rs_complete", "rs_coverage_sufficient", "rs_coverage_exhausted",
    "sis_complete", "sis_skipped_no_docs",
    "frd_complete", "frd_skipped_no_sis",
    "fis_error", "rs_error", "sis_error", "frd_error",
}

if triggered:
    endpoint, label = triggered
    try:
        resp = requests.post(f"{api_base}/api/cases/{active_case}/{endpoint}", timeout=10)
        if resp.status_code == 200:
            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown(f"""
            <div style="font-size: 13px; font-weight: 500; color: #1A73E8; margin-bottom: 12px;">
                {label} started — polling for completion…
            </div>
            """, unsafe_allow_html=True)

            progress_bar  = st.progress(0)
            status_slot   = st.empty()

            for i in range(120):  # 4-minute ceiling
                time.sleep(2)
                try:
                    poll = requests.get(
                        f"{api_base}/api/cases/{active_case}/status", timeout=5
                    )
                    if poll.status_code != 200:
                        continue
                    pd_data = poll.json()
                    cur     = pd_data.get("status", "")
                    done    = cur in _TERMINAL

                    pct = 1.0 if done else min((i + 1) / 60, 0.95)
                    progress_bar.progress(pct)

                    tl_now = pd_data.get("frd_traffic_light")
                    tl_str = f" · Traffic light: **{tl_now.upper()}**" if tl_now else ""

                    if any(s in cur for s in ["complete", "extracted", "sufficient"]):
                        chip_html = f'<span class="chip chip-green">{cur}</span>'
                    elif "error" in cur:
                        chip_html = f'<span class="chip chip-red">{cur}</span>'
                    else:
                        chip_html = f'<span class="chip chip-blue">{cur}</span>'

                    status_slot.markdown(
                        f"Status: {chip_html}&nbsp; Audit events: **{pd_data.get('audit_log_count', 0)}**{tl_str}",
                        unsafe_allow_html=True,
                    )

                    if done:
                        progress_bar.progress(1.0)
                        if "error" in cur:
                            st.error(f"{label} failed — status: {cur}")
                            for err in pd_data.get("errors", []):
                                st.error(err)
                        else:
                            st.success(f"{label} completed successfully.")
                            st.caption("Navigate to **Results** to view the analysis.")
                        break
                except Exception:
                    pass
            else:
                st.warning("Polling timed out. Check the Results page for the final status.")

        else:
            st.error(f"Could not start {label}: {resp.text}")

    except requests.ConnectionError:
        st.error("Cannot connect to API. Make sure the backend is running.")
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
