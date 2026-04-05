import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="DCA Forecast Beta", layout="centered")
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }</style>", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None
HOURS = [f"{i:02d}:00" for i in range(24)]

# --- 2. THE MILITANT DATA AUDITOR ---
def fetch_ndfd_data(lat, lon):
    try:
        # Step 1: NWS Grid Lookup
        p_res = requests.get(f"https://api.weather.gov/points/{lat},{lon}", timeout=10).json()
        forecast_url = p_res['properties']['forecastHourly']
        
        # Step 2: NWS Hourly Forecast
        w_res = requests.get(forecast_url, timeout=10).json()
        periods = w_res['properties']['periods'] # This is the LIST of hours
        
        # Step 3: USGS Little Falls (01646500)
        # Parameter 00065 = Height, 00010 = Water Temp
        u_url = "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00065,00010"
        u_res = requests.get(u_url, timeout=10).json()
        
        # Safe USGS Parsing
        height = u_res['value']['timeSeries']['values']['value']['value']
        w_temp_c = u_res['value']['timeSeries']['values']['value']['value']
        w_temp_f = round((float(w_temp_c) * 9/5) + 32)
        
        return periods, height, w_temp_f
    except Exception as e:
        st.error(f"Auditor Offline: {e}")
        return None, "3.9", 55

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac River DCA Forecast")
    if st.button("FLYING SCOTT - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Flying Scott", 'gate'; st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Cruiser", 'gate'; st.rerun()
    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# --- SCREEN 2: GATEWAY ---
elif st.session_state.page == 'gate':
    st.title(f"Logistics: {st.session_state.boat}")
    st.warning("Review SCOW requirements before proceeding.")
    c1 = st.checkbox("Review [Maintenance Notes](https://scow.org/page-1863774)")
    c2 = st.checkbox("Confirm [Reservation Slot](https://scow.org/page-1863774)")
    c3 = st.checkbox("Review [Weather/Nav links](https://scow.org)")
    if st.button("PROCEED TO FLOAT PLAN"):
        if c1 and c2 and c3: st.session_state.page = 'input'; st.rerun()
    if st.button("BACK"): st.session_state.page = 'home'; st.rerun()

# --- SCREEN 3: FLOAT PLAN ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    st.markdown("⚠️ *Note: Dynamic forecasts up to 48-hours only.*")
    sel_date = st.date_input("Select Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start", HOURS, index=13)
    with t_col2: end_t = st.selectbox("End", HOURS, index=18)
    if st.button("GENERATE DASHBOARD"):
        st.session_state.date, st.session_state.start, st.session_state.end = sel_date, start_t, end_t
        st.session_state.page = 'dashboard'; st.rerun()

# --- SCREEN 4: DASHBOARD (Restored Structure) ---
elif st.session_state.page == 'dashboard':
    periods, flow_ft, water_f = fetch_ndfd_data(38.85, -77.04)
    
    if periods:
        target = datetime.combine(st.session_state.date, datetime.strptime(st.session_state.start, "%H:%M").time())
        # Find the exact hour in the list
        p = periods
        for item in periods:
            start_iso = item['startTime'].replace('Z', '+00:00')
            if datetime.fromisoformat(start_iso).replace(tzinfo=None) >= target:
                p = item
                break
        
        # Extraction & Formatting
        wind = int(str(p['windSpeed']).split(' '))
        gust = int(str(p['windGust']).split(' ')) if p['windGust'] else wind
        w_dir = p['windDirection']
        rain = p.get('probabilityOfPrecipitation', {}).get('value', 0) or 0
        
        # Status Logic
        w_status = "🟢 GO"
        if st.session_state.boat == "Flying Scott":
            if gust >= 19: w_status = "🔴 NO-GO"
            elif gust >= 15: w_status = "🟡 CAUTION"
        else:
            if gust >= 29: w_status = "🔴 NO-GO"
            elif gust >= 20: w_status = "🟡 CAUTION"
        
        r_status = "🔴
