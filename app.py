import streamlit as st
from datetime import datetime
import requests

# --- 1. API SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
# Using the 2026 Stable Production Endpoint
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={API_KEY}"

# --- 2. STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. INITIALIZE STATE ---
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None
if 'weather_data' not in st.session_state: st.session_state.weather_data = ""

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep (DCA)")
    st.subheader("Select Your Craft")
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
    col1, col2 = st.columns(2)
    with col1: start_t = st.selectbox("Start Time", ["12:00", "13:00", "14:00", "15:00"], index=1)
    with col2: end_t = st.selectbox("End Time", ["16:00", "17:00", "18:00", "19:00"], index=2)
    
    if st.button("GET FORECAST"):
        with st.spinner("Analyzing Potomac conditions..."):
            try:
                prompt = (f"Provide a sailing weather brief for Potomac River (DCA) for {sel_date} "
                          f"between {start_t} and {end_t}. Include Wind mph/dir, Gusts, Temp, "
                          "Flow cfs, and Tides. Format with bold headings. "
                          "Add a 'Skipper Recommendation' for a Flying Scott vs a Cruiser.")
                
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                response = requests.post(API_URL, json=payload, timeout=30)
                data = response.json()
                
                # --- THE "STABILITY" EXTRACTION ---
                # This works even if Google adds more lists or layers
                if 'candidates' in data:
                    candidate = data['candidates']
                    content = candidate.get('content', candidate) # Fallback for different API versions
                    parts = content.get('parts', [content])
                    st.session_state.weather_data = parts.get('text', "Error: Text not found in response.")
                    st.session_state.page = 'dashboard'
                    st.rerun()
                else:
                    st.error(f"API Error: {data.get('error', {}).get('message', 'Unknown Error')}")
            except Exception as e:
                st.error(f"Connection Error: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Skipper's Briefing")
    st.markdown(st.session_state.weather_data)
    st.divider()
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
