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
    st.subheader("Select Your Location & Craft")
    if st.button("FLYING SCOTT - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Flying Scott", 'gate'
        st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Cruiser", 'gate'
        st.rerun()
    # Annapolis is back to being inactive and grey per your request
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: LOGISTICS ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    c1 = st.checkbox("Review [Maintenance Notes](https://scow.org/page-1863774)")
    c2 = st.checkbox("Confirm [Reservation Slot](https://scow.org/page-1863774)")
    c3 = st.checkbox("Review [Weather/Nav links](https://scow.org)")
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()
    if st.button("BACK"):
        st.session_state.page = 'home'
        st.rerun()

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    sel_date = st.date_input("Select Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start Time", ["12:00", "13:00", "14:00", "15:00"], index=1)
    with t_col2: end_t = st.selectbox("End Time", ["16:00", "17:00", "18:00", "19:00"], index=2)
    
    if st.button("GET FORECAST"):
        with st.spinner("Generating Dashboard..."):
            try:
                # Force the AI to output a clean Table for the metrics
                prompt = (f"Provide a sailing weather brief for Potomac (DCA) on {sel_date} "
                          f"between {start_t} and {end_t}. \n\n"
                          "REQUIRED FORMAT:\n"
                          "1. A Markdown table with columns: Metric | Value | Notes. "
                          "Include rows for Wind, Gusts, Temp, Flow (cfs), and Tides.\n"
                          "2. A 'Skipper Recommendation' section for a Flying Scott vs a Cruiser.")
                
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                response = requests.post(API_URL, json=payload, timeout=30)
                data = response.json()
                
                # Robust extraction for the Paid Tier
                briefing = data['candidates']['content']['parts']['text']
                st.session_state.weather_data = briefing
                st.session_state.page = 'dashboard'
                st.rerun()
            except Exception as e:
                st.error(f"System Error: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Weather Briefing")
    st.markdown(st.session_state.weather_data)
    st.divider()
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
