import streamlit as st
from datetime import datetime
import requests

# --- 1. API SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={API_KEY}"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. INITIALIZE STATE ---
if 'page' not in st.session_state:
    st.session_state.page = 'home'
if 'boat' not in st.session_state:
    st.session_state.boat = None
if 'weather_data' not in st.session_state:
    st.session_state.weather_data = ""

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep (DCA)")
    st.subheader("Select Your Craft")
    if st.button("FLYING SCOTT - POTOMAC"):
        st.session_state.boat = "Flying Scott"
        st.session_state.page = 'gate'
        st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat = "Cruiser"
        st.session_state.page = 'gate'
        st.rerun()
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: LOGISTICS ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    c1 = st.checkbox("I have reviewed [Maintenance Notes](https://scow.org/page-1863774).")
    c2 = st.checkbox("I have confirmed my [Reservation Slot](https://scow.org/page-1863774).")
    c3 = st.checkbox("I have reviewed [Weather/Nav links](https://scow.org).")
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
    col1, col2 = st.columns(2)
    with col1:
        st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    with col2:
        st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("GET FORECAST"):
        with st.spinner("Gemini is analyzing Potomac conditions..."):
            try:
                payload = {
                    "contents": [{"parts": [{"text": (
                        f"Provide a sailing weather brief for Potomac River (DCA) on {sel_date}. "
                        "Include: Wind mph/direction, Gusts, Temp, Precip %, Thunder risk, "
                        "River Flow cfs, and next two Tides. Format with bold headings. "
                        "Add a 'Skipper Recommendation' for a Flying Scott vs a Cruiser.")}]}]
                }
                response = requests.post(API_URL, json=payload, timeout=15)
                data = response.json()
                
                # --- MANUAL PRECISION EXTRACTION ---
                if 'candidates' in data and isinstance(data['candidates'], list):
                    # Step 1: Open the 'candidates' list
                    candidate = data['candidates']
                    # Step 2: Open the 'content' dictionary
                    content = candidate['content']
                    # Step 3: Open the 'parts' list
                    parts = content['parts']
                    # Step 4: Grab the 'text' string
                    text_blob = parts['text']
                    
                    st.session_state.weather_data = text_blob
                    st.session_state.page = 'dashboard'
                    st.rerun()
                elif 'error' in data:
                    st.error(f"Gemini Error: {data['error']['message']}")
            except Exception as e:
                st.error(f"Data Unpacking Error: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Skipper's Briefing")
    if st.session_state.weather_data:
        st.markdown(st.session_state.weather_data)
    st.divider()
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
