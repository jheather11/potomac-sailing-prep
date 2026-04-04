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
    sel_date = st.date_input("Select Date", datetime.now())
    col1, col2 = st.columns(2)
    with col1: st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    with col2: st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("GET FORECAST"):
        with st.spinner("Analyzing Potomac conditions (this may take 20s)..."):
            try:
                payload = {"contents": [{"parts": [{"text": f"Sailing weather brief for Potomac (DCA) on {sel_date}. Wind mph, Gusts, Temp, Flow cfs, Tides. Bold headings. Skipper Rec for Flying Scott vs Cruiser."}]}]}
                # Increased timeout to 30 seconds
                response = requests.post(API_URL, json=payload, timeout=30)
                data = response.json()
                
                if 'candidates' in data:
                    st.session_state.weather_data = data['candidates']['content']['parts']['text']
                    st.session_state.page = 'dashboard'
                    st.rerun()
                else:
                    st.error("AI Busy. Please wait 10 seconds and click 'Get Forecast' again.")
            except requests.exceptions.Timeout:
                st.error("The connection timed out. The Potomac is a busy place! Please try again.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown(st.session_state.weather_data)
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
