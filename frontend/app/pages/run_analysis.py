"""Run Analysis page — pipeline execution, guidance input, live audit trail."""

import textwrap
import time
import requests


def _html(s: str) -> str:
    """Strip common leading whitespace to prevent Markdown code-block detection."""
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

# ── Stage helpers ─────────────────────────────────────────────────────────────
_TERMINAL_STAGE_MAP = {
    "fis": {"fis_features_extracted", "fis_ingestion_skipped"},
    "rs":  {"rs_complete", "rs_coverage_sufficient", "rs_coverage_exhausted"},
    "sis": {"sis_complete", "sis_skipped_no_docs"},
    "frd": {"frd_complete", "frd_skipped_no_sis"},
}
_ALL_TERMINAL = {
    "fis_features_extracted", "fis_ingestion_skipped",
    "rs_complete", "rs_coverage_sufficient", "rs_coverage_exhausted",
    "sis_complete", "sis_skipped_no_docs",
    "frd_complete", "frd_skipped_no_sis",
    "fis_error", "rs_error", "sis_error", "frd_error",
}
_STAGES = [
    ("fis", "Financial Ingestion",   "Parse documents, compute ratios and Altman Z-Score.",
     "description"),
    ("rs",  "External Retrieval",    "Search news, filings, and market signals.",
     "language"),
    ("sis", "Signal Intelligence",   "Extract and verify risk signals from sources.",
     "neurology"),
    ("frd", "Risk Decisioning",      "Produce traffic-light verdict and report.",
     "gavel"),
]
_STAGE_ORDER = ["fis", "rs", "sis", "frd"]


def _stages_complete(status: str) -> int:
    count = 0
    for stage, terminals in _TERMINAL_STAGE_MAP.items():
        if status in terminals or f"{stage}_error" in status:
            count += 1
    return count


def _stage_is_done(status: str, prefix: str) -> bool:
    """Return True if this stage has completed (directly or because a later stage is active)."""
    if status in _TERMINAL_STAGE_MAP.get(prefix, set()):
        return True
    if f"{prefix}_error" in status:
        return False
    idx = _STAGE_ORDER.index(prefix) if prefix in _STAGE_ORDER else -1
    for later in _STAGE_ORDER[idx + 1:]:
        later_terminals = _TERMINAL_STAGE_MAP.get(later, set())
        if (status in later_terminals
                or f"{later}_running" in status
                or f"{later}_started" in status
                or f"{later}_error" in status):
            return True
    return False


def _stage_chip(status: str, prefix: str) -> str:
    if _stage_is_done(status, prefix):
        return '<span class="chip chip-green">Done</span>'
    if f"{prefix}_error" in status:
        return '<span class="chip chip-red">Error</span>'
    if f"{prefix}_running" in status or f"{prefix}_started" in status:
        return '<span class="chip chip-blue">Running</span>'
    return '<span class="chip chip-gray">Pending</span>'


def _stage_top_color(status: str, prefix: str) -> str:
    if _stage_is_done(status, prefix):
        return "#15803d"
    if f"{prefix}_error" in status:
        return "#b70100"
    if f"{prefix}_running" in status or f"{prefix}_started" in status:
        return "#2563eb"
    return "#eae7e7"


# ── Renderers for live-updating slots ─────────────────────────────────────────
def _render_circle_svg(pct: float, tl, status: str) -> str:
    _TL_STROKE = {"green": "#15803d", "amber": "#d97706", "red": "#b70100"}
    stroke_color = _TL_STROKE.get(tl or "", "#b70100")
    pct_int      = int(pct * 100)
    dashoffset   = 880 * (1 - pct)
    sub_label    = tl.upper() if tl else status.replace("_", " ").upper()
    return f"""
<div style="position:relative;width:320px;height:320px;flex-shrink:0;margin:0 auto;">
  <svg style="position:absolute;inset:0;width:100%;height:100%;transform:rotate(-90deg);"
       viewBox="0 0 320 320">
    <circle cx="160" cy="160" r="140" fill="transparent"
            stroke="#eae7e7" stroke-width="12"/>
    <circle cx="160" cy="160" r="140" fill="transparent"
            stroke="{stroke_color}" stroke-width="12"
            stroke-dasharray="880" stroke-dashoffset="{dashoffset:.1f}"
            stroke-linecap="round"/>
  </svg>
  <div style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;text-align:center;">
    <span style="font-family:'Manrope',sans-serif;font-size:4.5rem;font-weight:800;
                 color:#1c1b1b;line-height:1;font-variant-numeric:tabular-nums;">
      {pct_int}<span style="font-size:2rem;color:{stroke_color};">%</span>
    </span>
    <span style="font-family:'Inter',sans-serif;font-size:0.6875rem;font-weight:700;
                 text-transform:uppercase;letter-spacing:0.15em;color:#5f5e5e;
                 margin-top:0.5rem;">{sub_label}</span>
  </div>
</div>
"""


def _render_stage_cards(status: str) -> str:
    html = ""
    for prefix, name, desc, icon in _STAGES:
        chip      = _stage_chip(status, prefix)
        top_color = _stage_top_color(status, prefix)
        prog_frac = 1.0 if top_color == "#15803d" else (
                    0.5 if top_color == "#2563eb" else 0.0)
        html += f"""
<div style="background:#f6f3f2;border-radius:0.75rem;padding:1.25rem;
            margin-bottom:0.75rem;border-top:3px solid {top_color};">
  <div style="display:flex;align-items:center;justify-content:space-between;
              margin-bottom:0.75rem;">
    <span class="material-symbols-outlined" style="color:#b70100;">{icon}</span>
    {chip}
  </div>
  <div style="font-family:'Manrope',sans-serif;font-weight:700;font-size:0.9375rem;
              color:#1c1b1b;margin-bottom:0.25rem;">{name}</div>
  <div style="font-size:0.75rem;color:#5f5e5e;line-height:1.45;margin-bottom:0.75rem;">
    {desc}
  </div>
  <div style="height:3px;background:#eae7e7;border-radius:9999px;overflow:hidden;">
    <div style="height:100%;width:{int(prog_frac*100)}%;
                background:linear-gradient(135deg,#b70100,#e60000);
                border-radius:9999px;"></div>
  </div>
</div>
"""
    return html


def _render_terminal(audit_log: list) -> str:
    _BADGE_COLOR = {
        "fis": ("#b70100", "INIT"),
        "rs":  ("#60a5fa", "RETRIEVE"),
        "sis": ("#4ade80", "COMPUTE"),
        "frd": ("#eab308", "QUERY"),
    }
    rows_html = ""
    if audit_log:
        for evt in audit_log[-40:]:
            node   = evt.get("node_name", "")
            event  = evt.get("event", "")
            ts     = str(evt.get("timestamp", ""))[:19].replace("T", " ")
            prefix = node.split("_")[0].lower() if "_" in node else node[:3].lower()
            color, badge_lbl = _BADGE_COLOR.get(prefix, ("#d4d0ce", node.upper()[:6]))
            rows_html += (
                f'<div style="display:flex;gap:1rem;padding:5px 0;'
                f'border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<span style="color:rgba(212,208,206,0.35);font-size:0.6875rem;'
                f'white-space:nowrap;flex-shrink:0;">{ts}</span>'
                f'<span style="color:{color};font-weight:700;font-size:0.6875rem;'
                f'flex-shrink:0;">{badge_lbl}</span>'
                f'<span style="color:#d4d0ce;font-size:0.8125rem;">{event}</span>'
                f'</div>'
            )
    else:
        rows_html = (
            '<div style="color:rgba(212,208,206,0.4);font-style:italic;'
            'font-size:0.875rem;padding:1rem 0;">'
            'No audit events yet. Run a pipeline stage to begin.</div>'
        )
    return f"""
<div class="terminal-card">
  <div class="terminal-header">
    <span class="material-symbols-outlined" style="color:#b70100;font-size:1rem;">terminal</span>
    <span style="font-size:0.625rem;font-weight:700;text-transform:uppercase;
                 letter-spacing:0.15em;">Process_Kernel_V4.0</span>
  </div>
  <div class="terminal-body">{rows_html}</div>
</div>
"""


# ── Fetch initial state ────────────────────────────────────────────────────────
status_data            = None
current_status         = "unknown"
analyst_guidance_saved = ""
audit_log              = []

try:
    r = requests.get(f"{api_base}/api/cases/{active_case}/status", timeout=5)
    if r.status_code == 200:
        status_data    = r.json()
        current_status = status_data.get("status", "unknown")
except Exception:
    pass

try:
    r2 = requests.get(f"{api_base}/api/cases/{active_case}/result", timeout=5)
    if r2.status_code == 200:
        body                   = r2.json()
        analyst_guidance_saved = body.get("analyst_guidance") or ""
        audit_log              = body.get("audit_log", [])
except Exception:
    pass

tl    = (status_data or {}).get("frd_traffic_light")
pct   = _stages_complete(current_status) / 4

# ── Hero (breadcrumb + title + guidance | circle) ─────────────────────────────
left_col, right_col = st.columns([7, 5], gap="large")

with left_col:
    st.markdown(_html(f"""
    <div class="page-breadcrumb">
      <span>Credit Assessment</span>
      <span style="margin:0 0.25rem;color:#5f5e5e;">›</span>
      <span class="bc-active">Run Analysis</span>
    </div>
    <h1 style="font-family:'Manrope',sans-serif;font-size:3rem;font-weight:800;
               letter-spacing:-0.04em;color:#1c1b1b;line-height:1.05;margin-bottom:1rem;">
      Credit Risk Assessment
      <span style="color:#b70100;">{active_case}</span>
    </h1>
    <p style="color:#5f5e5e;font-size:1.0625rem;line-height:1.65;max-width:560px;
              margin-bottom:1.75rem;">
      Execute the AI-driven credit assessment pipeline. Each stage processes financial
      data, retrieves external signals, and synthesises a final risk verdict.
    </p>
    """), unsafe_allow_html=True)

    st.markdown(_html("""
    <label style="display:block;font-family:'Inter',sans-serif;font-size:0.6875rem;
                  font-weight:700;text-transform:uppercase;letter-spacing:0.1em;
                  color:#5f5e5e;margin-bottom:0.5rem;">Special Instructions</label>
    """), unsafe_allow_html=True)
    guidance_input = st.text_area(
        "Special Instructions",
        value=analyst_guidance_saved,
        placeholder="e.g. Focus on liquidity risk, the pending litigation, or ESG factors…",
        height=96,
        label_visibility="collapsed",
    )

    col_save, col_run_all = st.columns([2, 4], gap="medium")
    with col_save:
        save_btn = st.button("Save Guidance", use_container_width=True)
    with col_run_all:
        run_all = st.button("▶  Run Full Pipeline", use_container_width=True, type="primary")

    if save_btn:
        try:
            resp = requests.post(
                f"{api_base}/api/cases/{active_case}/guidance",
                json={"guidance": guidance_input},
                timeout=5,
            )
            if resp.status_code == 200:
                st.markdown('<span class="chip chip-green">Guidance saved</span>',
                            unsafe_allow_html=True)
            else:
                st.error("Failed to save guidance.")
        except Exception as exc:
            st.error(str(exc))

# Progress circle slot — lives in right column
with right_col:
    progress_slot = st.empty()
    progress_slot.markdown(_render_circle_svg(pct, tl, current_status), unsafe_allow_html=True)

# ── Audit trail + stage cards ─────────────────────────────────────────────────
st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1.25rem;">
  <div>
    <div class="section-label" style="margin-bottom:0.25rem;">
      <div class="section-label-bar"></div>
      <div class="section-label-text">Audit Trail &amp; Observability</div>
    </div>
    <p style="font-size:0.8125rem;color:#5f5e5e;margin:0;">
      Real-time breakdown of pipeline execution and data retrieval.
    </p>
  </div>
  <div style="display:flex;align-items:center;gap:0.5rem;padding:0.25rem 0.875rem;
              background:#f6f3f2;border-radius:9999px;">
    <span style="width:0.5rem;height:0.5rem;border-radius:9999px;background:#22c55e;
                 display:inline-block;"></span>
    <span style="font-size:0.625rem;font-weight:700;text-transform:uppercase;
                 letter-spacing:0.12em;color:#5f3f3a;">Live Feed</span>
  </div>
</div>
""", unsafe_allow_html=True)

audit_col, cards_col = st.columns([2, 1], gap="large")

with audit_col:
    terminal_slot = st.empty()
    terminal_slot.markdown(_render_terminal(audit_log), unsafe_allow_html=True)

with cards_col:
    stage_slot = st.empty()
    stage_slot.markdown(_render_stage_cards(current_status), unsafe_allow_html=True)

# ── Metrics strip ─────────────────────────────────────────────────────────────
st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4, gap="small")

audit_count = (status_data or {}).get("audit_log_count", len(audit_log))
warn_count  = len((status_data or {}).get("warnings", []))
err_count   = len((status_data or {}).get("errors", []))

for col, label, value in [
    (m1, "Current Stage",  current_status.replace("_", " ")),
    (m2, "Audit Events",   str(audit_count)),
    (m3, "Warnings",       str(warn_count)),
    (m4, "Errors",         str(err_count)),
]:
    with col:
        st.markdown(_html(f"""
        <div style="background:#fcf9f8;border-radius:0.75rem;padding:1.25rem 1.5rem;
                    border:1px solid rgba(233,188,181,0.12);
                    box-shadow:0 1px 3px rgba(28,27,27,0.06);">
          <p style="font-size:0.625rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.12em;color:#5f5e5e;margin-bottom:0.375rem;">{label}</p>
          <p style="font-family:'Manrope',sans-serif;font-size:1.5rem;font-weight:700;
                    color:#1c1b1b;font-variant-numeric:tabular-nums;margin:0;">{value}</p>
        </div>
        """), unsafe_allow_html=True)

for err in (status_data or {}).get("errors", []):
    st.error(err)

# ── Individual stage buttons ──────────────────────────────────────────────────
st.markdown("<div style='height:1.25rem;'></div>", unsafe_allow_html=True)
st.markdown("""
<div class="section-label">
  <div class="section-label-bar"></div>
  <div class="section-label-text">Run Individual Stages</div>
</div>
""", unsafe_allow_html=True)

b1, b2, b3, b4 = st.columns(4, gap="small")
with b1:
    run_fis = st.button("Run FIS", use_container_width=True,
                        help="Parse documents, compute Z-Score and ratios.")
with b2:
    run_rs = st.button("Run RS", use_container_width=True,
                       help="Search external sources for credit signals.")
with b3:
    run_sis = st.button("Run SIS", use_container_width=True,
                        help="Extract and verify risk signals.")
with b4:
    run_frd = st.button("Run FRD", use_container_width=True,
                        help="Produce traffic-light verdict.")

# ── Dispatch + polling ────────────────────────────────────────────────────────
triggered = None
if run_fis:   triggered = ("run-fis",  "FIS")
elif run_rs:  triggered = ("run-rs",   "RS")
elif run_sis: triggered = ("run-sis",  "SIS")
elif run_frd: triggered = ("run-frd",  "FRD")
elif run_all: triggered = ("run-all",  "Full pipeline")

if triggered:
    endpoint, label = triggered
    try:
        resp = requests.post(f"{api_base}/api/cases/{active_case}/{endpoint}", timeout=10)
        if resp.status_code == 200:
            st.markdown(_html(f"""
            <div style="margin-top:1.25rem;font-family:'Manrope',sans-serif;font-size:0.9375rem;
                        font-weight:600;color:#b70100;">
              {label} started — polling for completion…
            </div>
            """), unsafe_allow_html=True)

            poll_bar   = st.progress(0)
            poll_status = st.empty()

            for i in range(120):
                time.sleep(2)
                try:
                    poll    = requests.get(
                        f"{api_base}/api/cases/{active_case}/status", timeout=5
                    )
                    if poll.status_code != 200:
                        continue
                    pd_data    = poll.json()
                    new_status = pd_data.get("status", "")
                    new_tl     = pd_data.get("frd_traffic_light")
                    done       = new_status in _ALL_TERMINAL

                    pct_poll = 1.0 if done else min((i + 1) / 60, 0.95)
                    poll_bar.progress(pct_poll)

                    # ── Live update: circle + stage cards + terminal ──────────
                    new_pct = _stages_complete(new_status) / 4
                    progress_slot.markdown(
                        _render_circle_svg(new_pct, new_tl, new_status),
                        unsafe_allow_html=True,
                    )
                    stage_slot.markdown(
                        _render_stage_cards(new_status),
                        unsafe_allow_html=True,
                    )
                    # Refresh audit log
                    try:
                        r3 = requests.get(
                            f"{api_base}/api/cases/{active_case}/result", timeout=5
                        )
                        if r3.status_code == 200:
                            new_log = r3.json().get("audit_log", [])
                            terminal_slot.markdown(
                                _render_terminal(new_log), unsafe_allow_html=True
                            )
                    except Exception:
                        pass

                    if any(s in new_status for s in ["complete", "extracted", "sufficient"]):
                        chip_now = f'<span class="chip chip-green">{new_status}</span>'
                    elif "error" in new_status:
                        chip_now = f'<span class="chip chip-red">{new_status}</span>'
                    else:
                        chip_now = f'<span class="chip chip-blue">{new_status}</span>'

                    tl_str = f" · Traffic light: **{new_tl.upper()}**" if new_tl else ""
                    poll_status.markdown(
                        f"Status: {chip_now}&nbsp; Audit events: **{pd_data.get('audit_log_count', 0)}**{tl_str}",
                        unsafe_allow_html=True,
                    )

                    if done:
                        poll_bar.progress(1.0)
                        if "error" in new_status:
                            st.error(f"{label} failed — status: {new_status}")
                            for e in pd_data.get("errors", []):
                                st.error(e)
                        else:
                            st.success(f"{label} completed successfully.")
                            st.caption("Navigate to Results Dashboard to view the analysis.")
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
