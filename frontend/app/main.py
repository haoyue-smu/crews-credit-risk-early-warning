"""UBS Credit Assessment Platform — Streamlit Frontend.

Multi-page application for credit risk analysis:
  1. Create Case — Company intake form
  2. Upload Documents — File uploader
  3. Run Analysis — Execute FIS/RS with live status polling
  4. Results — Financial features, Z-Score, ratios, audit log
"""

import os
import streamlit as st

_PAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")

st.set_page_config(
    page_title="UBS Credit Assessment",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for premium look
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }
    
    /* Header styling */
    .hero-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    
    .hero-subtitle {
        color: #6b7280;
        font-size: 1rem;
        font-weight: 400;
        margin-bottom: 2rem;
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }
    
    .metric-card h3 {
        font-size: 0.85rem;
        color: #64748b;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.3rem;
    }
    
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1e293b;
    }
    
    /* Z-Score zone badges */
    .zone-safe {
        background: #dcfce7;
        color: #166534;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    .zone-grey {
        background: #fef3c7;
        color: #92400e;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    .zone-distress {
        background: #fecaca;
        color: #991b1b;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    
    .status-running {
        background: #dbeafe;
        color: #1e40af;
    }
    
    .status-complete {
        background: #dcfce7;
        color: #166534;
    }
    
    .status-error {
        background: #fecaca;
        color: #991b1b;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e1b4b 0%, #312e81 100%);
    }
    
    [data-testid="stSidebar"] .css-17lntkn,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #e0e7ff !important;
    }
    
    /* Divider */
    .section-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.markdown("## 🏦 UBS Credit")
st.sidebar.markdown("*Agentic Risk Analysis*")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["🏠 Dashboard", "📋 Create Case", "📄 Upload Documents", "🚀 Run Analysis", "📊 Results"],
    label_visibility="collapsed",
)

# Store API base URL
API_BASE = st.sidebar.text_input("API URL", value="http://localhost:8000", help="FastAPI backend URL")
st.session_state["api_base"] = API_BASE

# Main content
st.markdown('<p class="hero-title">UBS Credit Assessment Platform</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-subtitle">Agentic AI-powered credit risk analysis for wealth management</p>', unsafe_allow_html=True)

if page == "🏠 Dashboard":
    st.markdown("### Welcome")
    st.markdown("""
    This platform uses **agentic AI** to analyze company creditworthiness by combining:
    
    - 📑 **Financial Ingestion (FIS)** — Parse XML/XBRL/PDF financial documents, extract metrics, compute Altman Z-Scores
    - 🔍 **External Retrieval (RS)** — Search news, filings, forums, and social media for credit-relevant signals
    - 🧠 **Signal Intelligence (SIS)** — Extract and verify risk signals from retrieved documents
    - ⚖️ **Fusion & Risk Decisioning (FRD)** — Aggregate all evidence into a final credit recommendation
    
    **Get started** by creating a case in the sidebar navigation.
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="metric-card">
            <h3>Supported Formats</h3>
            <div class="value">XML · XBRL · PDF</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="metric-card">
            <h3>Z-Score Variants</h3>
            <div class="value">3 Altman Models</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="metric-card">
            <h3>Coverage Topics</h3>
            <div class="value">8+ Dynamic</div>
        </div>
        """, unsafe_allow_html=True)

elif page == "📋 Create Case":
    exec(open(os.path.join(_PAGES_DIR, "create_case.py"), encoding="utf-8").read())

elif page == "📄 Upload Documents":
    exec(open(os.path.join(_PAGES_DIR, "upload_documents.py"), encoding="utf-8").read())

elif page == "🚀 Run Analysis":
    exec(open(os.path.join(_PAGES_DIR, "run_analysis.py"), encoding="utf-8").read())

elif page == "📊 Results":
    exec(open(os.path.join(_PAGES_DIR, "results.py"), encoding="utf-8").read())