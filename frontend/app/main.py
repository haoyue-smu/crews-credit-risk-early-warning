import streamlit as st
import requests

st.set_page_config(page_title="Credit Assessment", layout="wide")
st.title("Agentic Credit Assessment")

entity_name = st.text_input("Entity Name")
entity_type = st.selectbox("Entity Type", ["business", "individual"])
location = st.text_input("Location")

if st.button("Assess"):
    payload = {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "location": location
    }

    try:
        response = requests.post("http://127.0.0.1:8000/api/assess", json=payload, timeout=30)
        response.raise_for_status()
        st.success("Assessment completed")
        st.json(response.json())
    except requests.RequestException as e:
        st.error(f"Request failed: {e}")