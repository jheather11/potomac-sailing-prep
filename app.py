import streamlit as st
from datetime import datetime
import requests

# --- 1. API SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
# Using 'v1' (Stable) instead of 'v1beta' to avoid the 404
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

# --- 2. INITIALIZE STATE ---
if 'page' not in st.session_state:
    st.session_state.page = 'home'
if 'boat' not in st.session_state:
    st.session_state.boat = None
if 'weather_data' not in st.session_state:
    st.session_state.weather_data = ""

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep (DCA)")
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
    c1 = st.checkbox("I have reviewed [Maintenance Notes](https://scow.org/page-1863774).")
    c2 = st.checkbox("I have confirmed my [Reservation Slot](https://scow.org/page-1863774).")
    c3 = st.checkbox("I have reviewed [Weather/Nav links](https://scow.org).")
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    sel_date = st.date_input("Select Date", datetime.now())
    
    if st.button("GET FORECAST"):
        with st.spinner("Analyzing Potomac conditions..."):
            try:
                payload = {
                    "contents": [{"parts": [{"text": f"Provide a sailing weather brief for Potomac River (DCA) on {sel_date}. Include Wind, Gusts, Temp, Precip %, Flow cfs, and Tides."}]}]
                }
                response = requests.post(API_URL, json=payload)
                data = response.json()
                
                # Robust check for the 'candidates' key
                if 'candidates' in data:
                    st.session_state.weather_data = data['candidates']['content']['parts']['text']
                    st.session_state.page = 'dashboard'
                    st.rerun()
                else:
                    st.error(f"API Error: {data.get('error', {}).get('message', 'Unknown Error')}")
            except Exception as e:
                st.error(f"Connection Failed: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.write(st.session_state.weather_data)
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
