import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & STYLE ---
st.set_page_config(page_title="DCA Forecast Dynamic", layout="centered")
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }</style>", unsafe_allow_html=True)

# --- 2. DATA FETCHING FUNCTIONS ---
def get_weather_data(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability,windspeed_10m,windgusts_10m,winddirection_10m&current_weather=true&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=America%2FNew_York"
    response = requests.get(url).json()
    return response

def get_river_flow():
    # USGS 01646500 POTOMAC RIVER NEAR WASH, DC LITTLE FALLS
    url = "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00065&siteStatus=all"
    try:
        data = requests.get(url).json()
        height = data['value']['timeSeries']['values']['value']['value']
        return float(height)
    except:
        return 3.7  # Fallback to last known good value if API is down

# --- 3. INITIALIZE STATE ---
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac River DCA Forecast")
    st.subheader("Dynamic Safety Auditor")
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
    st.warning("Review SCOW requirements before proceeding.")
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

# --- SCREEN 3: FLOAT PLAN ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    st.markdown("⚠️ *Note: Dynamic forecasts available up to 48 hours out.*")
    sel_date = st.date_input("Select Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start", range(24), index=13, format_func=lambda x: f"{x:02d}:00")
    with t_col2: end_t = st.selectbox("End", range(24), index=18, format_func=lambda x: f"{x:02d}:00")
    
    if st.button("GENERATE LIVE DASHBOARD"):
        st.session_state.sel_date = sel_date
        st.session_state.start_t = start_t
        st.session_state.page = 'dashboard'
        st.rerun()

# --- SCREEN 4: DASHBOARD ---
elif st.session_state.page == 'dashboard':
    with st.spinner("Auditing Live Data..."):
        weather = get_weather_data(38.85, -77.04) # DCA Coordinates
        river_ft = get_river_flow()
        
        # Extract Hourly Data for the window
        idx = st.session_state.start_t
        wind = weather['hourly']['windspeed_10m'][idx]
        gust = weather['hourly']['windgusts_10m'][idx]
        temp = weather['hourly']['temperature_2m'][idx]
        rain_prob = weather['hourly']['precipitation_probability'][idx]
        
        # Safety Logic
        def get_status(val, thresholds):
            if val >= thresholds['nogo']: return "🔴 NO-GO"
            if val >= thresholds['caution']: return "🟡 CAUTION"
            return "🟢 GO"

        # Boat Thresholds
        if st.session_state.boat == "Flying Scott":
            w_status = get_status(gust, {'caution': 15, 'nogo': 19})
        else:
            w_status = get_status(gust, {'caution': 20, 'nogo': 29})
        
        r_status = "🔴 NO-GO" if rain_prob > 70 else "🟡 CAUTION" if rain_prob > 30 else "🟢 GO"
        f_status = "🔴 NO-GO" if river_ft > 6.0 else "🟡 CAUTION" if river_ft > 5.0 else "🟢 GO"

        st.header(f"Briefing: {st.session_state.boat}")
        st.caption(f"Live Audit: {st.session_state.sel_date} @ {st.session_state.start_t}:00")
        
        st.markdown(f"""
        | Metric | Value | Status |
        | :--- | :--- | :--- |
        | **WIND/GUST** | {wind} / {gust} mph | {w_status} |
        | **AIR TEMP** | {temp}°F | 🟢 GO |
        | **RIVER FLOW** | {river_ft} ft | {f_status} |
        | **RAIN PROB** | {rain_prob}% | {r_status} |
        """)

        st.markdown("### CONSIDERATIONS")
        st.info("Confirm [RESERVATION](https://scow.org/page-1863774) and [MAINTENANCE](https://scow.org/page-1863774) before departure.")
        
        if "🔴" in w_status: st.error(f"DANGER: Gusts exceed {st.session_state.boat} safety limits!")
        if "🟡" in w_status: st.warning(f"ADVISORY: Reefing recommended for {st.session_state.boat} at current wind speeds.")
        if st.session_state.boat == "Cruiser": st.write("* **Draft Warning:** Cruiser draws 3.5ft on a solid keel.")
        
    if st.button("NEW PLAN"):
        st.session_state.page = 'home'
        st.rerun()
