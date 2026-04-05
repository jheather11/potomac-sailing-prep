import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. SETTINGS & STYLE ---
st.set_page_config(page_title="DCA Forecast Beta", layout="centered")
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }</style>", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None
HOURS = [f"{i:02d}:00" for i in range(24)]

# --- 2. DATA AUDITOR (NWS/USGS/NOAA) ---
def fetch_ndfd_data(lat, lon):
    try:
        # Step 1: Get the Grid Points
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        points_res = requests.get(points_url).json()
        forecast_url = points_res['properties']['forecastHourly']
        
        # Step 2: Get the Hourly Forecast
        weather_res = requests.get(forecast_url).json()
        periods = weather_res['properties']['periods']
        
        # Step 3: USGS Water Data (Little Falls 01646500)
        water_url = "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00065,00010"
        w_res = requests.get(water_url).json()
        height = w_res['value']['timeSeries']['values']['value']['value']
        w_temp_c = w_data = w_res['value']['timeSeries']['values']['value']['value']
        w_temp_f = (float(w_temp_c) * 9/5) + 32
        
        return periods, height, round(w_temp_f)
    except Exception as e:
        st.error(f"Data Retrieval Error: {e}")
        return None, "3.7", 52

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac River DCA Forecast")
    st.subheader("Select Craft")
    if st.button("FLYING SCOTT - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Flying Scott", 'gate'
        st.rerun()
    if st.button("CRUISER - POTOMAC"):
        st.session_state.boat, st.session_state.page = "Cruiser", 'gate'
        st.rerun()
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
    st.markdown("⚠️ *Note: Forecasts up to 48-hours into the future only.*")
    sel_date = st.date_input("Select Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start Time", HOURS, index=13)
    with t_col2: end_t = st.selectbox("End Time", HOURS, index=18)
    if st.button("VIEW DASHBOARD"):
        st.session_state.sel_date, st.session_state.start_t, st.session_state.end_t = sel_date, start_t, end_t
        st.session_state.page = 'dashboard'; st.rerun()
    if st.button("BACK"): st.session_state.page = 'gate'; st.rerun()

# --- SCREEN 4: DASHBOARD (Militant Audit) ---
elif st.session_state.page == 'dashboard':
    with st.spinner("Auditing NWS/USGS Data..."):
        raw_weather, flow_ft, water_f = fetch_ndfd_data(38.85, -77.04)
        
        if raw_weather:
            # ROBUST PARSING OF NWS ISO STRINGS
            target_dt = datetime.combine(st.session_state.sel_date, datetime.strptime(st.session_state.start_t, "%H:%M").time())
            
            # Find the first period that starts AFTER or AT our target time
            period = raw_weather
            for p in raw_weather:
                # Use fromisoformat which handles 'Z' and offsets in Python 3.11+
                p_start = datetime.fromisoformat(p['startTime'].replace('Z', '+00:00'))
                # Remove timezone for comparison to target_dt
                if p_start.replace(tzinfo=None) >= target_dt:
                    period = p
                    break
            
            # Extract Values
            wind_str = str(period['windSpeed']).split(' ')
            wind_val = int(wind_str)
            gust_val = int(str(period['windGust']).split(' ')) if period['windGust'] else wind_val
            w_dir = period['windDirection']
            temp_a = period['temperature']
            precip = period.get('probabilityOfPrecipitation', {}).get('value', 0)
            if precip is None: precip = 0
            
            # Status Logic
            w_status = "🟢 GO"
            if st.session_state.boat == "Flying Scott":
                if gust_val >= 19: w_status = "🔴 NO-GO"
                elif gust_val >= 15: w_status = "🟡 CAUTION"
            else:
                if gust_val >= 29: w_status = "🔴 NO-GO"
                elif gust_val >= 20: w_status = "🟡 CAUTION"
                
            r_status = "🔴 NO-GO" if precip > 70 else "🟡 CAUTION" if precip > 30 else "🟢 GO"
            wt_status = "🔴 NO-GO" if water_f < 54 else "🟡 CAUTION" if water_f < 60 else "🟢 GO"

            st.header(f"Briefing: {st.session_state.boat}")
            st.caption(f"Snapshot: {st.session_state.sel_date} | {st.session_state.start_t} to {st.session_state.end_t}")

            st.markdown(f"""
            | Metric | Value | Status |
            | :--- | :--- | :--- |
            | **WIND** | {wind_val} mph {w_dir} | {w_status} |
            | **GUSTS** | {gust_val} mph | {w_status} |
            | **TEMP (Air)** | {temp_a}°F | 🟢 GO |
            | **TEMP (Water)** | {water_f}°F | {wt_status} |
            | **FLOW** | {flow_ft} ft | 🟢 GO |
            | **TIDES** | High/Low TBD (Ebbing) | 🟡 CAUTION |
            | **RAIN** | {precip}% | {r_status} |
            | **THUNDER** | {period['shortForecast']} | {"🔴 NO-GO" if "Thunder" in period['shortForecast'] else "🟢 GO"} |
            """)

            st.markdown("### CONSIDERATIONS")
            st.info("Before departing, confirm [RESERVATION](https://scow.org/page-1863774), [MAINTENANCE](https://scow.org/page-1863774), and [WEATHER / NAV links](https://scow.org).")
            
            if st.session_state.boat == "Cruiser":
                st.write("* **Draft Warning:** Cruiser draws 3.5ft on a solid keel.")
            if "🟡" in w_status or "🔴" in w_status:
                st.write(f"* **Wind Alert:** Gusts are {gust_val} mph. Reefing is advised for {st.session_state.boat} at designated thresholds.")
            if wt_status != "🟢 GO":
                st.write(f"* **Water Temp:** Water is {water_f}°F. Immersion risk is high.")
            st.write("* **Tides:** Caution advised; check return window for depth/current at marina entrance.")
        else:
            st.error("Audit Failed: The NWS API is not responding. Please try again in 1 minute.")

    st.divider()
    st.subheader("Share with Crew")
    st.code("https://potomac-dca-forecast.streamlit.app/", language=None)

    if st.button("NEW PLAN"):
        st.session_state.page = 'home'
        st.rerun()
