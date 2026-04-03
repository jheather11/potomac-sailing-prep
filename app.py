import streamlit as st
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

# --- INITIALIZE STATE ---
if 'page' not in st.session_state:
    st.session_state.page = 'home'
if 'boat' not in st.session_state:
    st.session_state.boat = None

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
        
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: HARD GATE ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics Check: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    st.markdown("[Open SCOW Reservations](https://www.scow.org/page-1863774)")
    st.markdown("[Open SCOW Weather & Nav](https://www.scow.org)")
    
    c1 = st.checkbox("I have reviewed Maintenance Notes for this craft.")
    c2 = st.checkbox("I have confirmed my Reservation Time Slot.")
    c3 = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")
    
    if st.button("PROCEED TO MISSION PARAMETERS"):
        if c1 and c2 and c3:
            st.session_state.page = 'input'
            st.rerun()
        else:
            st.error("Please check all boxes to proceed.")
    
    if st.button("BACK"):
        st.session_state.page = 'home'
        st.rerun()

# --- SCREEN 3: INPUT ---
elif st.session_state.page == 'input':
    st.title("Mission Parameters")
    st.date_input("Date", datetime.now())
    st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("CALCULATE CONDITIONS"):
        st.session_state.page = 'dashboard'
        st.rerun()

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.success("STATUS: GO")
    
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
    
    # Wind logic for Considerations
    with st.expander("🛡️ SAFETY & LIMITS", expanded=True):
        if st.session_state.boat == "Cruiser":
            st.write("• Gusts at 24 mph: **Consider Reefing**.")
        st.write("• Flow is 38% below average (LOW).")
        
    with st.expander("🧭 NAVIGATION"):
        st.write("• Tide dropping to 0.08ft. Watch depth at Marina entrance.")
        st.write("• Wind against Tide: Expect steep surface chop.")
    
    if st.button("SHARE WITH CREW"):
        st.info("Briefing copied to clipboard (Simulated)")
    
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
