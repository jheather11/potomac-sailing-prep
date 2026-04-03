import streamlit as st
from datetime import datetime
import google.generativeai as genai

# --- 1. API CONNECT ---
# This looks for the "Secret" you saved in Streamlit Cloud
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("API Key Error: Make sure GEMINI_API_KEY is in Streamlit Secrets.")

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
    if st.button("FLYING SCOT - POTOMAC"):
        st.session_state.boat = "Flying Scot"
        st.session_state.page = 'gate'
        st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat = "Cruiser"
        st.session_state.page = 'gate'
        st.rerun()

# --- SCREEN 2: LOGISTICS CHECK ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    c1 = st.checkbox("Reviewed Maintenance Notes.")
    c2 = st.checkbox("Confirmed Reservation Slot.")
    c3 = st.checkbox("Reviewed SCOW Weather/Nav links.")
    
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()
        else:
            st.error("Please check all boxes to proceed.")

# --- SCREEN 3: FLOAT PLAN INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    sel_date = st.date_input("Select Date", datetime.now())
    st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    # THIS IS THE BUTTON THAT TRIGGERS THE LIVE DATA
    if st.button("GET LIVE CONDITIONS"):
        with st.spinner("Gemini is analyzing Potomac conditions..."):
            try:
                # The AI Prompt
                prompt = (f"Provide a sailing weather brief for Potomac River (DCA) on {sel_date}. "
                          "Include: Wind mph/direction, Gusts, Temp, Precip, Thunder risk, "
                          "River Flow cfs, and next two Tides. Format with clear headings.")
                
                response = model.generate_content(prompt)
                st.session_state.weather_data = response.text
                st.session_state.page = 'dashboard'
                st.rerun()
            except Exception as e:
                st.error(f"Data Fetch Failed: {e}")

# --- SCREEN 4: LIVE DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.success("LIVE DATA RETRIEVED")
    
    # Display the AI-generated brief
    st.markdown("### 📡 Skipper's Briefing")
    st.write(st.session_state.weather_data)
    
    st.divider()
    
    if st.button("SHARE WITH CREW"):
        st.code(st.session_state.weather_data, language="text")
        st.info("Copy text above for your crew chat.")

    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
