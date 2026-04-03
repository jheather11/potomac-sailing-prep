import streamlit as st
import pandas as pd
from datetime import datetime

# --- APP CONFIG ---
st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="centered")

# --- STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- SCREEN 1: HOME ---
if 'page' not in st.session_state:
    st.session_state.page = 'home'

def change_page(name):
    st.session_state.page = name

if st.session_state.page == 'home':
    st.title("⛵ Potomac Sail Prep (DCA)")
    st.subheader("Select Your Craft")
    if st.button("FLYING SCOT - POTOMAC"):
        st.session_state.boat = "Flying Scot"
        change_page('gate')
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat = "Cruiser"
        change_page('gate')
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: HARD GATE ---
elif st.session_state.page == 'gate':
    st.title("Logistics Check")
    st.info("Check official SCOW sources before proceeding.")
    st.markdown("[Open SCOW Reservations](https://www.scow.org/page-1863774)")
    st.markdown("[Open SCOW Weather & Nav](https://www.scow.org)")
    
    c1 = st.checkbox("I have reviewed Maintenance Notes for this craft.")
    c2 = st.checkbox("I have confirmed my Reservation Time Slot.")
    c3 = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")
    
    if st.button("PROCEED TO MISSION PARAMETERS"):
        if c1 and c2 and c3:
            change_page('input')
        else:
            st.error("Please check all boxes to proceed.")

# --- SCREEN 3: INPUT ---
elif st.session_state.page == 'input':
    st.title("Mission Parameters")
    date = st.date_input("Date", datetime.now())
    start = st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    end = st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("CALCULATE CONDITIONS"):
        change_page('dashboard')

# --- SCREEN 4: DASHBOARD (BETA SIMULATION) ---
elif st.session_state.page == 'dashboard':
    st.title("Dashboard")
    st.success("STATUS: GO")
    
    # Mock Data for Beta Testing
    col1, col2 = st.columns(2)
    with col1:
        st.metric("WIND", "14-16 (G24) S-SW")
        st.metric("TEMP", "78°-82°F")
        st.metric("TIDE 1", "4:59 PM (Low)", "OUTGOING")
    with col2:
        st.metric("FLOW", "9,780 cfs", "-38% (LOW)")
        st.metric("PRECIP", "15% / None")
        st.metric("TIDE 2", "10:15 PM (High)", "INCOMING")

    st.divider()
    st.subheader("Considerations")
    with st.expander("🛡️ SAFETY & LIMITS", expanded=True):
        st.write("• Gusts at 24 mph: **Consider Reefing**.")
        st.write("• Flow is 38% below average (LOW).")
    with st.expander("🧭 NAVIGATION"):
        st.write("• Tide dropping to 0.08ft. Watch depth at Marina.")
        st.write("• Wind against Tide: Expect building chop.")
    
    if st.button("SHARE WITH CREW"):
        st.info("Briefing copied to clipboard (Simulated)")
    
    if st.button("START OVER"):
        change_page('home')
