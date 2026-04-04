import streamlit as st
from datetime import datetime
import requests

# --- 1. API SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={API_KEY}"

# --- 2. STYLE ---
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }</style>", unsafe_allow_html=True)

# --- 3. INITIALIZE STATE ---
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None
if 'weather_data' not in st.session_state: st.session_state.weather_data = ""

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep (DCA)")
    if st.button("FLYING SCOTT - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Flying Scott", 'gate'
        st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Cruiser", 'gate'
        st.rerun()
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: LOGISTICS ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    c1 = st.checkbox("Review Maintenance Notes")
    c2 = st.checkbox("Confirm Reservation Slot")
    c3 = st.checkbox("Review Weather/Nav links")
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    st.date_input("Select Date", datetime.now())
    
    # Restored and simplified time layout
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.selectbox("Start Time", ["12:00", "13:00", "14:00", "15:00"], index=1)
    with t_col2:
        st.selectbox("End Time", ["16:00", "17:00", "18:00", "19:00"], index=2)
    
    if st.button("GET FORECAST"):
        with st.spinner("Fetching your Skipper's Briefing..."):
            try:
                payload = {"contents": [{"parts": [{"text": "Provide a sailing weather brief for Potomac River (DCA) for today. Wind mph/dir, Gusts, Temp, Flow cfs, and Tides. Include a Skipper Recommendation for a Flying Scott vs a Cruiser."}]}]}
                response = requests.post(API_URL, json=payload, timeout=30)
                data = response.json()
                
                # --- THE EXACT EXTRACTION (Based on your debug image) ---
                # data -> candidates (list) -> -> content (dict) -> parts (list) -> -> text (str)
                briefing_text = data['candidates']['content']['parts']['text']
                
                st.session_state.weather_data = briefing_text
                st.session_state.page = 'dashboard'
                st.rerun()
            except Exception as e:
                st.error("The Potomac is choppy! Refresh and try once more.")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Skipper's Briefing")
    st.markdown(st.session_state.weather_data)
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
