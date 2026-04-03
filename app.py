import streamlit as st
from datetime import datetime
import google.generativeai as genai

# --- 1. API CONNECT (THE STABILITY FIX) ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Switching to 'gemini-pro' - the most widely supported stable name across all API versions
    model = genai.GenerativeModel('gemini-pro')
except Exception as e:
    st.error(f"API Setup Error: {e}")

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
                # Targeted prompt for the Saturday test
                prompt = (f"Act as a professional sailing weather expert. Provide a "
                          f"detailed sailing weather brief for the Potomac River (DCA) on {sel_date}. "
                          "Include: Wind speed/direction, Gusts, Temp, Precipitation %, Thunder risk, "
                          "River Flow in cfs, and the next two Tides. "
                          "Format with clear headings. "
                          "Add a 'Skipper Recommendation' for a Flying Scott vs a Cruiser.")
                
                response = model.generate_content(prompt)
                st.session_state.weather_data = response.text
                st.session_state.page = 'dashboard'
                st.rerun()
            except Exception as e:
                st.error(f"Data Fetch Failed: {e}. Ensure your API Key is active in Google AI Studio.")

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.markdown("### 📡 Skipper's Briefing")
    st.write(st.session_state.weather_data)
    st.divider()
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
