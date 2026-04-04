import streamlit as st
from datetime import datetime
import requests

# --- 1. API SETUP ---
API_KEY = st.secrets["GEMINI_API_KEY"]
API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={API_KEY}"

# --- 2. STYLE (Mobile Optimized) ---
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; } iframe { width: 100% !important; } .reportview-container .main .block-container{ padding-top: 1rem; }</style>", unsafe_allow_html=True)

# --- 3. INITIALIZE STATE ---
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None
if 'weather_data' not in st.session_state: st.session_state.weather_data = ""

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep")
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
    c1 = st.checkbox("Review [Maintenance Notes](https://scow.org/page-1863774)")
    c2 = st.checkbox("Confirm [Reservation Slot](https://scow.org/page-1863774)")
    c3 = st.checkbox("Review [Weather/Nav links](https://scow.org)")
    if st.button("PROCEED"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()
    if st.button("BACK"):
        st.session_state.page = 'home'
        st.rerun()

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    sel_date = st.date_input("Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start", ["12:00", "13:00", "14:00", "15:00"], index=1)
    with t_col2: end_t = st.selectbox("End", ["16:00", "17:00", "18:00", "19:00"], index=2)
    
    if st.button("GET DASHBOARD"):
        with st.spinner("Loading..."):
            try:
                # THE "STRICT" PROMPT
                prompt = (f"Act as a professional sailing weather officer. Provide a concise brief for Potomac (DCA) "
                          f"on {sel_date} from {start_t} to {end_t}. \n\n"
                          "STRICT FORMATTING RULES:\n"
                          "1. DO NOT include any introductory text or disclaimers.\n"
                          "2. START immediately with a Markdown table (Metric | Value | Notes) "
                          "for Wind, Gusts, Temp, Flow (cfs), and Tides.\n"
                          "3. END with two short bullet points for Skipper Recommendations (Flying Scott vs Cruiser).\n"
                          "4. Keep it under 200 words total for smartphone readability.")
                
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                response = requests.post(API_URL, json=payload, timeout=30)
                data = response.json()
                
                def find_text(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k == 'text': return v
                            res = find_text(v)
                            if res: return res
                    elif isinstance(obj, list):
                        for item in obj:
                            res = find_text(item)
                            if res: return res
                    return None

                result = find_text(data)
                if result:
                    st.session_state.weather_data = result
                    st.session_state.page = 'dashboard'
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.header(f"Briefing: {st.session_state.boat}")
    st.markdown(st.session_state.weather_data)
    if st.button("NEW PLAN"):
        st.session_state.page = 'home'
        st.rerun()
