"""Credit Assessment Platform — Streamlit frontend entry point."""

import os
import streamlit as st

_PAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")

st.set_page_config(
    page_title="Credit Assessment",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS — Material Design 3 token set
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Roboto+Mono:wght@400;500&display=swap');

/* ── Reset & base ─────────────────────────────────────────────────────── */
html, body, [class*="css"], [class*="st-"] {
    font-family: 'Roboto', sans-serif !important;
}

/* Force light-mode text throughout — prevents Streamlit's theme from
   rendering dark text as near-white on a white background */
.stApp {
    background-color: #FFFFFF !important;
    color: #202124 !important;
}

.stApp p, .stApp span, .stApp div, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 {
    color: #202124;
}

/* Streamlit markdown / text components */
.stMarkdown, .stMarkdown p, .stMarkdown li,
.stMarkdownContainer, .stText {
    color: #202124 !important;
}

/* st.caption */
.stMarkdown small, small, .stCaption {
    color: #5F6368 !important;
}

/* st.metric label + value */
[data-testid="stMetricLabel"]  { color: #5F6368 !important; font-size: 12px !important; }
[data-testid="stMetricValue"]  { color: #202124 !important; }
[data-testid="stMetricDelta"]  { font-size: 12px !important; }

/* Tabs */
[data-testid="stTabs"] button { color: #5F6368 !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color: #1A73E8 !important; }

/* Expander */
details summary { color: #202124 !important; }

/* Input labels */
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stCheckbox"] label,
[data-testid="stFileUploader"] label {
    color: #202124 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* Input field text */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    color: #202124 !important;
    background: #FFFFFF !important;
}

/* Selectbox text */
[data-testid="stSelectbox"] > div > div {
    color: #202124 !important;
    background: #FFFFFF !important;
}

/* Dataframe */
[data-testid="stDataFrame"] { color: #202124; }

.main > .block-container {
    padding: 28px 36px 48px;
    max-width: 1280px;
    background-color: #FFFFFF;
}

/* ── Hide Streamlit chrome ────────────────────────────────────────────── */
[data-testid="stHeader"]     { display: none !important; }
footer                       { visibility: hidden !important; }
#MainMenu                    { display: none !important; }
.stDeployButton              { display: none !important; }

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E8EAED;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 0;
}

/* Sidebar text — force dark on white for all native elements */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label {
    color: #3C4043 !important;
}

/* API endpoint input label */
[data-testid="stSidebar"] [data-testid="stTextInput"] label {
    color: #5F6368 !important;
    font-size: 11px !important;
    font-weight: 400 !important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    color: #202124 !important;
    background: #FFFFFF !important;
    font-size: 12px !important;
}

/* Nav radio — remove label and hide circles */
[data-testid="stSidebar"] .stRadio > label {
    display: none;
}

[data-testid="stSidebar"] .stRadio > div {
    gap: 2px !important;
    flex-direction: column;
}

[data-testid="stSidebar"] .stRadio > div > label {
    display: flex;
    align-items: center;
    padding: 10px 20px !important;
    border-radius: 0 24px 24px 0 !important;
    margin-right: 12px !important;
    font-size: 14px !important;
    font-weight: 400 !important;
    color: #3C4043 !important;
    cursor: pointer;
    transition: background 0.1s;
    min-height: 44px;
}

[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(26,115,232,0.08) !important;
    color: #1A73E8 !important;
}

[data-testid="stSidebar"] .stRadio > div > label[data-baseweb="radio"] > div:first-child {
    display: none !important;
}

/* Active nav item */
[data-testid="stSidebar"] .stRadio [aria-checked="true"] {
    background: #E8F0FE !important;
    color: #1A73E8 !important;
    font-weight: 500 !important;
    border-radius: 0 24px 24px 0 !important;
    padding: 10px 20px !important;
    margin-right: 12px !important;
}

/* Radio option text within the checked item */
[data-testid="stSidebar"] .stRadio [aria-checked="true"] p,
[data-testid="stSidebar"] .stRadio [aria-checked="true"] span,
[data-testid="stSidebar"] .stRadio [aria-checked="true"] div {
    color: #1A73E8 !important;
}

/* ── Cards ────────────────────────────────────────────────────────────── */
.card {
    background: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 16px;
}

.card-elevated {
    background: #FFFFFF;
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(60,64,67,.3), 0 2px 6px 2px rgba(60,64,67,.15);
    padding: 20px 24px;
    margin-bottom: 16px;
}

/* ── Status chips ─────────────────────────────────────────────────────── */
.chip {
    display: inline-flex;
    align-items: center;
    height: 22px;
    padding: 0 10px;
    border-radius: 11px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    white-space: nowrap;
    vertical-align: middle;
}

.chip-blue   { background: #E8F0FE; color: #1967D2; }
.chip-green  { background: #E6F4EA; color: #137333; }
.chip-red    { background: #FCE8E6; color: #C5221F; }
.chip-yellow { background: #FEF7E0; color: #B06000; }
.chip-gray   { background: #F1F3F4; color: #5F6368; }

/* ── Z-score zone pills ───────────────────────────────────────────────── */
.zone-safe     { background: #E6F4EA; color: #137333; padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; display: inline-block; }
.zone-grey     { background: #FEF7E0; color: #B06000; padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; display: inline-block; }
.zone-distress { background: #FCE8E6; color: #C5221F; padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; display: inline-block; }

/* ── Traffic light hero ───────────────────────────────────────────────── */
.tl-hero {
    border-radius: 12px;
    padding: 40px;
    text-align: center;
    margin-bottom: 24px;
}
.tl-hero .tl-icon    { font-size: 56px; line-height: 1; margin-bottom: 8px; }
.tl-hero .tl-verdict { font-size: 38px; font-weight: 300; letter-spacing: -1px; margin: 4px 0 8px; }
.tl-hero .tl-sub     { font-size: 13px; font-weight: 400; opacity: 0.75; }

.tl-green  { background: #E6F4EA; color: #137333; }
.tl-amber  { background: #FEF7E0; color: #B06000; }
.tl-red    { background: #FCE8E6; color: #C5221F; }
.tl-gray   { background: #F1F3F4; color: #5F6368; }

/* ── Page header ──────────────────────────────────────────────────────── */
.page-header {
    margin-bottom: 28px;
    padding-bottom: 20px;
    border-bottom: 1px solid #E8EAED;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}

.page-header h1 {
    font-size: 22px;
    font-weight: 400;
    color: #202124;
    margin: 0 0 4px;
    letter-spacing: -0.2px;
}

.page-header p {
    font-size: 13px;
    color: #5F6368;
    margin: 0;
}

/* ── Section label ────────────────────────────────────────────────────── */
.section-label {
    font-size: 11px;
    font-weight: 500;
    color: #1A73E8;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin: 28px 0 12px;
}

/* ── Pipeline stage card ──────────────────────────────────────────────── */
.stage-card {
    background: #FFFFFF;
    border: 1px solid #DADCE0;
    border-radius: 8px;
    padding: 16px;
    position: relative;
    overflow: hidden;
}

.stage-card::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 3px;
    background: #DADCE0;
}

.stage-card.s-complete::after { background: #188038; }
.stage-card.s-running::after  { background: #1A73E8; }
.stage-card.s-error::after    { background: #D93025; }

.stage-card .s-name  { font-size: 13px; font-weight: 500; color: #202124; margin-bottom: 2px; }
.stage-card .s-desc  { font-size: 11px; color: #5F6368; line-height: 1.4; }
.stage-card .s-icon  { font-size: 22px; margin-bottom: 8px; }

/* ── Empty state ──────────────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 60px 24px;
}
.empty-state .es-icon  { font-size: 40px; color: #DADCE0; margin-bottom: 12px; }
.empty-state .es-title { font-size: 16px; font-weight: 500; color: #3C4043; margin-bottom: 6px; }
.empty-state .es-body  { font-size: 13px; color: #5F6368; }

/* ── Monospace code snippets ──────────────────────────────────────────── */
.mono {
    font-family: 'Roboto Mono', monospace;
    font-size: 12px;
    background: #F1F3F4;
    padding: 1px 6px;
    border-radius: 4px;
    color: #1967D2;
}

/* ── Divider ──────────────────────────────────────────────────────────── */
.divider { height: 1px; background: #E8EAED; border: none; margin: 24px 0; }

/* ── Case row in list ─────────────────────────────────────────────────── */
.case-row {
    display: flex;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #F1F3F4;
    gap: 12px;
}
.case-row:last-child { border-bottom: none; }
.case-row .cr-name { font-size: 14px; font-weight: 500; color: #202124; }
.case-row .cr-id   { font-size: 11px; font-family: 'Roboto Mono', monospace; color: #5F6368; }

/* ── Doc row ──────────────────────────────────────────────────────────── */
.doc-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid #F1F3F4;
}
.doc-row:last-child { border-bottom: none; }

/* ── Streamlit form submit button ─────────────────────────────────────── */
div[data-testid="stForm"] .stButton > button[kind="primaryFormSubmit"] {
    background: #1A73E8;
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: 500;
    letter-spacing: 0.25px;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 20px 16px; border-bottom: 1px solid #E8EAED; margin-bottom: 4px;">
        <div style="font-size: 16px; font-weight: 500; color: #1A73E8; letter-spacing: -0.2px;">
            Credit Assessment
        </div>
        <div style="font-size: 11px; color: #5F6368; margin-top: 3px; letter-spacing: 0.2px;">
            Agentic Risk Platform
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "nav",
        ["Dashboard", "Create Case", "Upload Documents", "Run Analysis", "Results"],
        label_visibility="collapsed",
    )

    st.markdown('<div style="height: 1px; background: #E8EAED; margin: 12px 0;"></div>', unsafe_allow_html=True)

    # Active case display
    active_case = st.session_state.get("active_case_id")
    if active_case:
        st.markdown(f"""
        <div style="padding: 12px 20px;">
            <div style="font-size: 10px; font-weight: 500; color: #5F6368; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 4px;">
                Active Case
            </div>
            <div style="font-size: 12px; font-family: 'Roboto Mono', monospace; color: #1967D2;
                        background: #E8F0FE; padding: 4px 8px; border-radius: 4px; word-break: break-all;">
                {active_case}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="padding: 12px 20px;">
            <div style="font-size: 11px; color: #9AA0A6; font-style: italic;">No active case</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height: 1px; background: #E8EAED; margin: 4px 0 12px;"></div>', unsafe_allow_html=True)

    API_BASE = st.text_input(
        "API endpoint",
        value=st.session_state.get("api_base", "http://localhost:8000"),
        label_visibility="visible",
    )
    st.session_state["api_base"] = API_BASE

# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

if page == "Dashboard":
    st.markdown("""
    <div style="margin-bottom: 32px;">
        <h1 style="font-size: 28px; font-weight: 300; color: #202124; margin: 0 0 6px; letter-spacing: -0.5px;">
            Credit Assessment Platform
        </h1>
        <p style="font-size: 14px; color: #5F6368; margin: 0;">
            End-to-end agentic AI pipeline for corporate credit risk analysis
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline overview cards
    st.markdown('<p class="section-label">Pipeline stages</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    stages = [
        (c1, "FIS", "Financial Ingestion",
         "Parse XML / XBRL / PDF financials. Compute Altman Z-Score and financial ratios."),
        (c2, "RS", "External Retrieval",
         "Search news, filings, forums, and social media for credit-relevant signals."),
        (c3, "SIS", "Signal Intelligence",
         "Extract, verify, and de-conflict risk signals from retrieved documents."),
        (c4, "FRD", "Risk Decisioning",
         "Fuse all evidence into a traffic-light verdict and analyst narrative."),
    ]

    for col, abbr, name, desc in stages:
        with col:
            st.markdown(f"""
            <div class="card" style="height: 100%;">
                <div style="font-size: 11px; font-weight: 700; letter-spacing: 1px;
                            color: #1A73E8; margin-bottom: 6px;">{abbr}</div>
                <div style="font-size: 15px; font-weight: 500; color: #202124;
                            margin-bottom: 8px;">{name}</div>
                <div style="font-size: 12px; color: #5F6368; line-height: 1.5;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    # Quick-start guide
    st.markdown('<p class="section-label" style="margin-top: 32px;">Get started</p>', unsafe_allow_html=True)

    steps = [
        ("1", "Create a case", "Enter company details — name, type, industry, jurisdiction."),
        ("2", "Upload documents", "Attach annual reports in XML, XBRL, or PDF format."),
        ("3", "Run the pipeline", "Trigger FIS → RS → SIS → FRD or run each stage individually."),
        ("4", "Review results", "Inspect the traffic-light verdict, Z-Score, signals, and analyst report."),
    ]

    for num, title, desc in steps:
        st.markdown(f"""
        <div style="display: flex; align-items: flex-start; gap: 16px; padding: 12px 0;
                    border-bottom: 1px solid #F1F3F4;">
            <div style="width: 28px; height: 28px; border-radius: 50%; background: #E8F0FE;
                        color: #1A73E8; font-size: 13px; font-weight: 600; flex-shrink: 0;
                        display: flex; align-items: center; justify-content: center;">{num}</div>
            <div>
                <div style="font-size: 14px; font-weight: 500; color: #202124;">{title}</div>
                <div style="font-size: 12px; color: #5F6368; margin-top: 2px;">{desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

elif page == "Create Case":
    exec(open(os.path.join(_PAGES_DIR, "create_case.py"), encoding="utf-8").read())

elif page == "Upload Documents":
    exec(open(os.path.join(_PAGES_DIR, "upload_documents.py"), encoding="utf-8").read())

elif page == "Run Analysis":
    exec(open(os.path.join(_PAGES_DIR, "run_analysis.py"), encoding="utf-8").read())

elif page == "Results":
    exec(open(os.path.join(_PAGES_DIR, "results.py"), encoding="utf-8").read())
