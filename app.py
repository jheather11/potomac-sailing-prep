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

# --- SCREEN 2: LOGISTICS CHECK ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics Check: {st.session_state.boat}")
    st.info("Check official SCOW sources before proceeding.")
    st.markdown("[Open SCOW Reservations](https://www.scow.org/page-1863774)")
    st.markdown("[Open SCOW Weather & Nav](https://www.scow.org)")
    
    c1 = st.checkbox("I have reviewed Maintenance Notes for this craft.")
    c2 = st.checkbox("I have confirmed my Reservation Time Slot.")
    c3 = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")
    
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
    st.date_input("Date", datetime.now())
    st.time_input("Start Time", datetime.strptime("13:00", "%H:%M"))
    st.time_input("End Time", datetime.strptime("18:00", "%H:%M"))
    
    if st.button("CALCULATE CONDITIONS"):
        st.session_state.page = 'dashboard'
        st.rerun()

# --- SCREEN 4: DASHBOARD (Updated for April 5 Forecast) ---
elif st.session_state.page == 'dashboard':
    st.title(f"Dashboard: {st.session_state.boat}")
    st.warning("STATUS: CAUTION - SHOWERS LIKELY")
    
    # Custom Dashboard Table
    st.markdown(f"""
    | Metric | Forecast / Live Data (APR 5) | Status |
    | :--- | :--- | :--- |
    | **WIND** | 10–18 mph (Gust 28) S | **GO** ✅ |
    | **TEMP** | High near 74°F | **WARM** |
    | **PRECIP** | 100% / Showers Likely | **WET** |
    | **THUNDER** | NONE | **SAFE** |
    | **FLOW** | 10,200 cfs (35% below Avg) | **LOW** |
    | **TIDE 1** | 6:15 PM: 2.8 ft (High) | **INCOMING** |
    | **TIDE 2** | 12:45 PM: 0.1 ft (Low) | **OUTGOING** |
    """)

    st.divider()
    st.subheader("Considerations")
    
    with st.expander("🛡️ SAFETY & LIMITS", expanded=True):
        st.write("• Wind: Gusts up to **28 mph**. For Cruisers, **Consider Reefing**.")
        if st.session_state.boat == "Flying Scot":
            st.error("• WARNING: Gusts (28 mph) exceed Flying Scot limit (19 mph).")
        st.write("• Showers: 100% chance of rain. Check for visibility drops.")
        
    with st.expander("🧭 NAVIGATION"):
        st.write("• Tide: Strong **INCOMING** flood current for your entire afternoon sail.")
        st.write("• Wind Strategy: Steady South wind will build surface chop against the outgoing river flow.")
    
    if st.button("SHARE WITH CREW"):
        share_text = f"⛵ {st.session_state.boat} Float Plan: CAUTION\nWind: 10-18 (G28) S\nTide: High 6:15 PM (Incoming)\nPrecip: 100% Rain\nNote: Gusty day, bring foul weather gear!"
        st.code(share_text, language="text")
        st.info("Copy the text above to share with your crew.")
    
    if st.button("START OVER"):
        st.session_state.page = 'home'
        st.rerun()
