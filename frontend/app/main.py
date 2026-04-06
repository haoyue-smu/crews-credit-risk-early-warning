"""UBS Credit Assessment — Streamlit entry point.

Design system: "The Financial Atelier" matching reference_fe/*.html exactly.
"""

import os
import streamlit as st

st.set_page_config(
    page_title="UBS Credit Assessment",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "page" not in st.session_state:
    st.session_state["page"] = "case_entry"
if "api_base" not in st.session_state:
    st.session_state["api_base"] = os.getenv("API_BASE", "http://localhost:8000")
if "active_case_id" not in st.session_state:
    st.session_state["active_case_id"] = None

# ── Design system CSS ─────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">

<style>
/* ─── RESET & GLOBALS ────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

/* Hide all Streamlit chrome */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="collapsedControl"],
[data-testid="stSidebar"],
footer, #MainMenu { display: none !important; }

/* App background */
.stApp,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section,
.main,
.main > div {
    background-color: #fcf9f8 !important;
}

/* Block container */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 4rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1200px !important;
}

/* Global font + color */
body, .stApp, .stMarkdown, p, span, div, label, li, td, th {
    font-family: 'Inter', sans-serif !important;
    color: #1c1b1b !important;
}
h1, h2, h3, h4 {
    font-family: 'Manrope', sans-serif !important;
    color: #1c1b1b !important;
}

/* ─── MATERIAL SYMBOLS (must come AFTER global font rule) ────────────────── */
.material-symbols-outlined,
.msym {
    font-family: 'Material Symbols Outlined' !important;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    font-style: normal !important;
    font-size: 1.25rem;
    line-height: 1;
    letter-spacing: normal !important;
    word-wrap: normal !important;
    text-transform: none !important;
    white-space: nowrap;
    direction: ltr;
    -webkit-font-feature-settings: 'liga';
    font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
    display: inline-block;
    color: inherit !important;
}

/* ─── TERMINAL OVERRIDES (must come AFTER global color rule) ─────────────── */
.terminal-card .terminal-body,
.terminal-card .terminal-body *,
.terminal-card .terminal-body span,
.terminal-card .terminal-body div {
    color: #d4d0ce !important;
    font-family: 'Courier New', Courier, monospace !important;
}
.terminal-header,
.terminal-header * {
    color: #a8a29e !important;
}

/* ─── FORM CARD ──────────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: #ffffff !important;
    border-radius: 0.75rem !important;
    box-shadow: 0 8px 32px 0 rgba(28,27,27,0.06) !important;
    border: 1px solid rgba(233,188,181,0.15) !important;
    padding: 2rem 2.5rem !important;
}

/* ─── CHAT MESSAGE COLORS ────────────────────────────────────────────────── */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] div,
[data-testid="stChatMessage"] li {
    color: #1c1b1b !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9375rem !important;
}

/* ─── NAVIGATION ─────────────────────────────────────────────────────────── */
.ubs-nav-bar {
    position: sticky;
    top: 0;
    left: 0;
    right: 0;
    z-index: 9999;
    background: rgba(252, 249, 248, 0.85);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid rgba(226, 212, 212, 0.4);
    padding: 0 2rem;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0 -2rem;
    width: calc(100% + 4rem);
}
.ubs-nav-logo {
    font-family: 'Manrope', sans-serif !important;
    font-size: 1.375rem !important;
    font-weight: 800 !important;
    color: #b70100 !important;
    letter-spacing: -0.04em;
    line-height: 1;
}
.ubs-nav-links { display: flex; align-items: stretch; height: 64px; gap: 0; }
.ubs-nav-link {
    display: flex;
    align-items: center;
    padding: 0 1.25rem;
    font-family: 'Inter', sans-serif;
    font-size: 0.875rem;
    font-weight: 500;
    color: #5f5e5e !important;
    text-decoration: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    transition: color 0.2s, border-color 0.2s;
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;
    height: 100%;
}
.ubs-nav-link:hover { color: #1c1b1b !important; }
.ubs-nav-link.active {
    color: #b70100 !important;
    border-bottom-color: #b70100;
    font-weight: 600;
}
.ubs-nav-account {
    color: #5f5e5e !important;
    font-size: 1.5rem;
    vertical-align: middle;
}

/* Streamlit button resets for nav */
.nav-btn-wrap [data-testid="stButton"] > button {
    background: transparent !important;
    border-top: none !important;
    border-left: none !important;
    border-right: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: #5f5e5e !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    padding: 0 1.25rem !important;
    height: 64px !important;
    line-height: 64px !important;
    min-height: 0 !important;
    transition: color 0.2s, border-color 0.2s !important;
}
.nav-btn-wrap [data-testid="stButton"] > button:hover {
    color: #1c1b1b !important;
    background: transparent !important;
    border-bottom-color: rgba(183,1,0,0.2) !important;
}
.nav-btn-active [data-testid="stButton"] > button,
.nav-btn-active [data-testid="stButton"] > button:hover {
    color: #b70100 !important;
    border-bottom-color: #b70100 !important;
    font-weight: 600 !important;
    background: transparent !important;
}

/* ─── CARDS ──────────────────────────────────────────────────────────────── */
.card-white {
    background: #ffffff;
    border-radius: 0.75rem;
    box-shadow: 0 8px 32px 0 rgba(28, 27, 27, 0.06);
    border: 1px solid rgba(233, 188, 181, 0.15);
    padding: 2.5rem;
}
.card-surface-low {
    background: #f6f3f2;
    border-radius: 0.75rem;
    border: 1px solid rgba(233, 188, 181, 0.10);
    padding: 2.5rem;
}
.card-hero-outer {
    background: #f6f3f2;
    border-radius: 0.75rem;
    padding: 0.25rem;
    margin-bottom: 2rem;
}
.card-hero-inner {
    background: #ffffff;
    border-radius: 0.625rem;
    box-shadow: 0 8px 32px 0 rgba(28, 27, 27, 0.06);
    padding: 2rem 2.5rem;
}

/* ─── SECTION HEADERS ────────────────────────────────────────────────────── */
.section-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
}
.section-label-bar {
    width: 1.5px;
    height: 1.25rem;
    background: #b70100;
    border-radius: 2px;
    flex-shrink: 0;
}
.section-label-text {
    font-family: 'Manrope', sans-serif !important;
    font-size: 1.125rem !important;
    font-weight: 700 !important;
    color: #1c1b1b !important;
}

/* ─── PAGE HERO ──────────────────────────────────────────────────────────── */
.page-breadcrumb {
    font-family: 'Inter', sans-serif;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #5f5e5e;
    display: flex;
    align-items: center;
    gap: 0.375rem;
    margin-bottom: 1rem;
    margin-top: 2.5rem;
}
.page-breadcrumb span { color: #5f5e5e !important; }
.page-breadcrumb .bc-active { color: #b70100 !important; font-weight: 700; }
.page-heading {
    font-family: 'Manrope', sans-serif;
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    color: #1c1b1b;
    line-height: 1.05;
    margin-bottom: 1rem;
}
.page-subheading {
    font-family: 'Inter', sans-serif;
    font-size: 1.0625rem;
    color: #5f5e5e;
    line-height: 1.65;
    max-width: 640px;
    margin-bottom: 2rem;
}

/* ─── INPUTS ─────────────────────────────────────────────────────────────── */
/* Remove all Streamlit input default styling */
[data-testid="stTextInput"] > div,
[data-testid="stTextInput"] > div > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
[data-baseweb="input"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
}
[data-baseweb="input"]::after,
[data-baseweb="input"]::before { display: none !important; }

[data-testid="stTextInput"] input,
[data-baseweb="input"] input {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(233, 188, 181, 0.4) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    outline: none !important;
    padding: 1rem 0 !important;
    font-family: 'Manrope', sans-serif !important;
    font-size: 1.125rem !important;
    color: #1c1b1b !important;
    transition: border-color 0.2s !important;
}
[data-testid="stTextInput"] input:focus,
[data-baseweb="input"] input:focus {
    border-bottom: 2px solid #b70100 !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stTextInput"] input::placeholder {
    color: #c8c6c5 !important;
}

/* Input labels */
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stTextArea"] label,
[data-testid="stNumberInput"] label,
[data-testid="stCheckbox"] label {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.6875rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #5f5e5e !important;
    margin-bottom: 0.25rem !important;
}

/* Selectbox */
[data-testid="stSelectbox"] > div > div,
[data-baseweb="select"] > div {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(233, 188, 181, 0.4) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0.875rem 0 !important;
    color: #1c1b1b !important;
    font-family: 'Manrope', sans-serif !important;
    font-size: 1rem !important;
    cursor: pointer !important;
}
[data-baseweb="select"] > div:focus,
[data-baseweb="select"] > div[aria-expanded="true"] {
    border-bottom: 2px solid #b70100 !important;
    outline: none !important;
}
[data-baseweb="popover"] {
    border-radius: 0.5rem !important;
    box-shadow: 0 8px 32px rgba(28,27,27,0.12) !important;
    background: #ffffff !important;
}
[data-baseweb="popover"] * {
    background: #ffffff !important;
    color: #1c1b1b !important;
    font-family: 'Inter', sans-serif !important;
}
[data-baseweb="menu"] li,
[data-baseweb="menu"] [role="option"] {
    background: #ffffff !important;
    color: #1c1b1b !important;
}
[data-baseweb="menu"] li:hover,
[data-baseweb="menu"] [role="option"]:hover,
[data-baseweb="menu"] [aria-selected="true"] {
    background: #f6f3f2 !important;
    color: #b70100 !important;
}
[data-baseweb="select"] svg { fill: #5f5e5e !important; }

/* Textarea — wipe BaseWeb container first */
[data-testid="stTextArea"] > div,
[data-testid="stTextArea"] > div > div,
[data-baseweb="textarea"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0.5rem !important;
}
[data-testid="stTextArea"] > div > div > textarea,
[data-baseweb="textarea"] textarea {
    background: #f6f3f2 !important;
    border: none !important;
    border-bottom: 2px solid rgba(183,1,0,0.25) !important;
    border-radius: 0.5rem !important;
    box-shadow: none !important;
    outline: none !important;
    padding: 1rem !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9375rem !important;
    color: #5f5e5e !important;
    resize: none !important;
    transition: border-color 0.2s !important;
    width: 100% !important;
}
[data-testid="stTextArea"] > div > div > textarea:focus,
[data-baseweb="textarea"] textarea:focus {
    border-bottom: 2px solid #b70100 !important;
    outline: none !important;
    box-shadow: none !important;
}

/* ─── BUTTONS ────────────────────────────────────────────────────────────── */
/* In Streamlit 1.55 the <button> is NOT a direct child of the testid wrapper
   (BaseButtonTooltip wraps it), so use descendant selector (space), not >.    */

/* All buttons: light tonal default */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
    background: #e2dfde !important;
    color: #1c1b1b !important;
    border: none !important;
    border-radius: 0.625rem !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
    transition: background 0.15s, color 0.15s !important;
}
[data-testid="stButton"] button:hover,
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {
    background: #d5d3d2 !important;
    color: #1c1b1b !important;
}

/* Primary variant — must come after generic rule */
[data-testid="stButton"] button[kind="primary"],
[data-testid="stDownloadButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: linear-gradient(135deg, #b70100 0%, #e60000 100%) !important;
    color: #ffffff !important;
    border-radius: 0.75rem !important;
    box-shadow: 0 8px 32px 0 rgba(28,27,27,0.1) !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    padding: 0.875rem 2.5rem !important;
    letter-spacing: 0.01em !important;
}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stDownloadButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    opacity: 0.9 !important;
    background: linear-gradient(135deg, #b70100 0%, #e60000 100%) !important;
    color: #ffffff !important;
}
[data-testid="stButton"] button[kind="primary"]:active {
    transform: scale(0.98) !important;
}

/* File uploader browse button */
[data-testid="stFileUploaderDropzoneInput"] + div button,
[data-testid="stFileUploader"] button {
    background: #e2dfde !important;
    color: #1c1b1b !important;
    border: none !important;
    border-radius: 0.5rem !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
}

/* ─── FILE UPLOADER ──────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    background: #f6f3f2 !important;
    border: 2px dashed rgba(233, 188, 181, 0.5) !important;
    border-radius: 0.75rem !important;
    padding: 3rem !important;
    text-align: center !important;
    transition: border-color 0.2s !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: rgba(183, 1, 0, 0.4) !important;
}
[data-testid="stFileUploaderDropInstructions"] {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
    color: #1c1b1b !important;
}

/* ─── STATUS CHIPS ───────────────────────────────────────────────────────── */
.chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.15rem 0.625rem;
    border-radius: 9999px;
    font-family: 'Inter', sans-serif;
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.chip-red    { background: rgba(183,1,0,0.08);     color: #b70100 !important; }
.chip-amber  { background: rgba(217,119,6,0.10);  color: #d97706 !important; }
.chip-green  { background: rgba(21,128,61,0.08);  color: #15803d !important; }
.chip-blue   { background: rgba(37,99,235,0.08);  color: #2563eb !important; }
.chip-gray   { background: rgba(95,94,94,0.08);   color: #5f5e5e !important; }
.chip-primary{ background: rgba(183,1,0,0.08);    color: #b70100 !important; }

/* ─── TERMINAL CARD ──────────────────────────────────────────────────────── */
.terminal-card {
    background: #1c1b1b;
    border-radius: 0.75rem;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
}
.terminal-header {
    background: #2a2928;
    padding: 0.75rem 1.25rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-bottom: 1px solid #3a3836;
}
.terminal-body {
    padding: 1.25rem;
    font-family: 'Courier New', Courier, monospace !important;
    font-size: 0.8125rem;
    line-height: 1.65;
    color: #d4d0ce;
    max-height: 420px;
    overflow-y: auto;
}
.terminal-body * { color: inherit !important; font-family: inherit !important; }
.tl-time  { color: rgba(212,208,206,0.35) !important; font-size: 0.6875rem; flex-shrink: 0; }
.tl-init  { color: #b70100 !important; font-weight: 700; font-size: 0.6875rem; }
.tl-query { color: #eab308 !important; font-weight: 700; font-size: 0.6875rem; }
.tl-ret   { color: #60a5fa !important; font-weight: 700; font-size: 0.6875rem; }
.tl-comp  { color: #4ade80 !important; font-weight: 700; font-size: 0.6875rem; }
.tl-msg   { color: #d4d0ce !important; }
.tl-active{ background: rgba(183,1,0,0.06); border-left: 2px solid #b70100; padding-left: 0.75rem; }

/* ─── METRICS ────────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #fcf9f8 !important;
    border-radius: 0.75rem !important;
    box-shadow: 0 1px 3px rgba(28,27,27,0.06) !important;
    border: 1px solid rgba(233,188,181,0.12) !important;
    padding: 1.25rem 1.5rem !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.625rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: #5f5e5e !important;
}
[data-testid="stMetricValue"] {
    font-family: 'Manrope', sans-serif !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1c1b1b !important;
    font-variant-numeric: tabular-nums !important;
}

/* ─── EXPANDERS ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border-radius: 0.5rem !important;
    border: 1px solid rgba(233,188,181,0.15) !important;
    box-shadow: 0 4px 16px rgba(28,27,27,0.04) !important;
    margin-bottom: 0.5rem !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.9375rem !important;
    color: #1c1b1b !important;
    padding: 1rem 1.25rem !important;
}
/* Streamlit 1.55 renders all Material icons as [data-testid="stIconMaterial"] spans */
[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] {
    font-family: 'Material Symbols Outlined' !important;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
    font-style: normal !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased !important;
}

/* ─── TABS ───────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid rgba(233,188,181,0.2) !important;
    gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #5f5e5e !important;
    padding: 0.75rem 1.25rem !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #b70100 !important;
    border-bottom: 2px solid #b70100 !important;
    font-weight: 600 !important;
    background: transparent !important;
}


/* ─── CHAT ───────────────────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    background: #ffffff !important;
    border-top: 1px solid rgba(233,188,181,0.2) !important;
}
[data-testid="stChatInput"] textarea {
    font-family: 'Inter', sans-serif !important;
    color: #1c1b1b !important;
    font-size: 0.9375rem !important;
}
[data-testid="stChatMessage"] {
    background: #ffffff !important;
    border-radius: 0.625rem !important;
    border: 1px solid rgba(233,188,181,0.12) !important;
    box-shadow: 0 4px 16px rgba(28,27,27,0.04) !important;
}


/* ─── SUPPORTING DOCS CARD ───────────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #f6f3f2 !important;
    border-radius: 0.75rem !important;
    border: 1px solid rgba(233,188,181,0.15) !important;
}

/* ─── DIVIDERS ───────────────────────────────────────────────────────────── */
.atelier-hr {
    height: 1px;
    background: rgba(233, 188, 181, 0.2);
    margin: 2rem 0;
    border: none;
    display: block;
}

/* ─── SIGNAL CARDS ───────────────────────────────────────────────────────── */
.sig-card {
    background: #ffffff;
    border-radius: 0.5rem;
    box-shadow: 0 4px 16px rgba(28,27,27,0.05);
    border: 1px solid rgba(233,188,181,0.08);
    padding: 1rem 1.25rem;
    margin-bottom: 0.625rem;
    border-left: 4px solid #e9bcb5;
}
.sig-high    { border-left-color: #b70100; }
.sig-medium  { border-left-color: #b47800; }
.sig-low     { border-left-color: #5f5e5e; }
.sig-positive{ border-left-color: #15803d; }

/* ─── STAGE CARDS ────────────────────────────────────────────────────────── */
.stage-card {
    background: #ffffff;
    border-radius: 0.625rem;
    padding: 1rem 1.25rem;
    border: 1px solid rgba(233,188,181,0.1);
    border-top: 3px solid #eae7e7;
    box-shadow: 0 4px 16px rgba(28,27,27,0.04);
}
.stage-running  { border-top-color: #2563eb; }
.stage-complete { border-top-color: #15803d; }
.stage-error    { border-top-color: #b70100; }
.stage-abbr {
    font-size: 0.5625rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #b70100 !important;
}
.stage-name {
    font-family: 'Manrope', sans-serif;
    font-size: 0.875rem;
    font-weight: 700;
    color: #1c1b1b;
    margin-top: 0.375rem;
}
.stage-desc {
    font-size: 0.75rem;
    color: #5f5e5e;
    margin-top: 0.25rem;
    line-height: 1.4;
}

/* ─── DATA SOURCE CARDS ──────────────────────────────────────────────────── */
.source-card {
    background: #f6f3f2;
    border-radius: 0.75rem;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
    transition: transform 0.2s;
}
.source-card:hover { transform: translateX(2px); }

/* ─── MISC UTILS ─────────────────────────────────────────────────────────── */
.tabular-nums { font-variant-numeric: tabular-nums; }
.text-primary { color: #b70100 !important; }
.text-secondary { color: #5f5e5e !important; }
.gradient-primary { background: linear-gradient(135deg, #b70100 0%, #e60000 100%); }
.ambient-shadow { box-shadow: 0 8px 32px 0 rgba(28, 27, 27, 0.06); }
.msym {
    font-family: 'Material Symbols Outlined' !important;
    font-size: 1.25rem;
    vertical-align: middle;
    color: inherit !important;
}
</style>
""", unsafe_allow_html=True)


# ── Navigation ────────────────────────────────────────────────────────────────
def _render_nav():
    page = st.session_state.get("page", "case_entry")
    active = st.session_state.get("active_case_id")

    st.markdown("""
    <div class="ubs-nav-bar">
      <span class="ubs-nav-logo">UBS</span>
      <div style="flex:1;"></div>
      <span class="material-symbols-outlined ubs-nav-account" style="margin-left:1rem;">account_circle</span>
    </div>
    """, unsafe_allow_html=True)

    # Nav buttons immediately below, pulled up visually
    st.markdown('<div style="display:flex;justify-content:center;gap:0;margin-top:-4px;border-bottom:1px solid rgba(233,188,181,0.15);margin-bottom:0;">', unsafe_allow_html=True)
    _pages = [("case_entry","Case Entry"),("run_analysis","Run Analysis"),("results","Results Dashboard")]
    cols = st.columns(len(_pages) + 2)
    for col, (key, label) in zip(cols[1:-1], _pages):
        is_active = page == key
        wrap_cls = "nav-btn-active" if is_active else "nav-btn-wrap"
        with col:
            st.markdown(f'<div class="{wrap_cls}">', unsafe_allow_html=True)
            if st.button(label, key=f"_nav_{key}", use_container_width=True):
                st.session_state["page"] = key
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if active:
        st.markdown(f"""
        <div style="text-align:center;padding:6px 0 0;">
          <span class="chip chip-primary" style="font-size:0.5625rem;">
            <span class="msym" style="font-size:0.75rem;">folder_open</span>
            {active}
          </span>
        </div>
        """, unsafe_allow_html=True)


_render_nav()

# ── Route ─────────────────────────────────────────────────────────────────────
_PAGE_DIR = os.path.join(os.path.dirname(__file__), "pages")
_ROUTES = {
    "case_entry":   os.path.join(_PAGE_DIR, "case_entry.py"),
    "run_analysis": os.path.join(_PAGE_DIR, "run_analysis.py"),
    "results":      os.path.join(_PAGE_DIR, "results.py"),
}

_pf = _ROUTES.get(st.session_state["page"])
if _pf and os.path.exists(_pf):
    with open(_pf, encoding="utf-8") as _f:
        exec(_f.read(), globals())  # noqa: S102
else:
    st.error(f"Page not found: {st.session_state['page']}")
