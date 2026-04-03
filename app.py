import streamlit as st
from datetime import datetime
import google.generativeai as genai

# --- 1. API CONNECT ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Using the stable production name to avoid 404 version errors
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("API Key Error: Check your Streamlit Secrets for GEMINI_API_KEY.")

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

# --- SCREEN 2: LOGISTICS (With Embedded Links) ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    
    # Checkboxes with embedded links as requested
    c1 = st.checkbox("I have reviewed [Maintenance Notes](https://scow.org/page-1863774).")
    c2 = st.checkbox("I have confirmed my [Reservation Slot](https://scow.org/page-1863774).")
    c3 = st.checkbox("I have reviewed [Weather/Nav links](https://scow.org) on the SCOW homepage.")
    
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()
        else:
            st.error("Please check all boxes to proceed.")
            
    if st.button("BACK"):
        st.session_state.page = 'home'
        st.rerun()

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    sel_date = st.date_input("Select Date", datetime.now())
    st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("GET FORECAST"):
        with st.spinner("Gemini is analyzing Potomac conditions..."):
            try:
                # Targeted prompt for the Saturday/Sunday window
                prompt = (f"Provide a sailing weather brief for Potomac River (DCA) on {sel_date}. "
                          "Include: Wind mph/direction, Gusts, Temp, Precip, Thunder risk, "
                          "River Flow cfs, and next two Tides. Format with clear headings. "
                          "Add a 'Skipper Recommendation' note for a 19ft day sailor.")
                
                response = model.generate_content(prompt)
                st.session_state.weather_data = response.text
                st.session_state.page = 'dashboard'
                st.rerun()
            except Exception as e:
                st.error(f"Data Fetch Failed: {e}")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Skipper's Briefing")
    st.write(st.session_state.weather_data)
    st.divider()
    
    if st.button("SHARE WITH CREW"):
        st.code(st.session_state.weather_data, language="text")
        st.info("Copy the text above for your crew chat.")

    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
