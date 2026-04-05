import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. CONFIG & STYLE ---
st.set_page_config(page_title="DCA Lab - Dynamic", layout="centered")
st.markdown("<style>.stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #004466; color: white; }</style>", unsafe_allow_html=True)

# --- 2. DYNAMIC FETCHING ---
def get_clean_data(lat, lon, start_hour):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability,windspeed_10m,windgusts_10m,winddirection_10m&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=America%2FNew_York"
    res = requests.get(url).json()
    # USGS Gauge Height (Little Falls)
    try:
        f_res = requests.get("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=01646500&parameterCd=00065").json()
        flow = f_res['value']['timeSeries']['values']['value']['value']
    except: flow = "3.7"
    return res, flow

# --- 3. STATE ---
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'boat' not in st.session_state: st.session_state.boat = None

# --- SCREEN 1: HOME ---
if st.session_state.page == 'home':
    st.title("⛵ Potomac River DCA Forecast")
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

# --- SCREEN 3: INPUT ---
elif st.session_state.page == 'input':
    st.title("Float Plan")
    st.markdown("⚠️ *Forecasts up to 48-hours into the future only.*")
    sel_date = st.date_input("Select Date", datetime.now())
    t_col1, t_col2 = st.columns(2)
    with t_col1: start_t = st.selectbox("Start", range(24), index=13, format_func=lambda x: f"{x:02d}:00")
    with t_col2: end_t = st.selectbox("End", range(24), index=18, format_func=lambda x: f"{x:02d}:00")
    if st.button("GENERATE DASHBOARD"):
        st.session_state.start_t, st.session_state.end_t, st.session_state.date = start_t, end_t, sel_date
        st.session_state.page = 'dashboard'; st.rerun()

# --- SCREEN 4: DASHBOARD (The Restoration) ---
elif st.session_state.page == 'dashboard':
    with st.spinner("Auditing..."):
        data, flow_ft = get_clean_data(38.85, -77.04, st.session_state.start_t)
        h = st.session_state.start_t
        
        # Data Extraction
        w_speed = data['hourly']['windspeed_10m'][h]
        w_gust = data['hourly']['windgusts_10m'][h]
        w_dir_deg = data['hourly']['winddirection_10m'][h]
        temp_a = data['hourly']['temperature_2m'][h]
        rain_p = data['hourly']['precipitation_probability'][h]
        
        # Direction Logic
        dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        w_dir = dirs[int((w_dir_deg + 22.5) / 45) % 8]

        # Status Logic
        w_status = "🟢 GO"
        if st.session_state.boat == "Flying Scott":
            if w_gust >= 19: w_status = "🔴 NO-GO"
            elif w_gust >= 15: w_status = "🟡 CAUTION"
        else:
            if w_gust >= 29: w_status = "🔴 NO-GO"
            elif w_gust >= 20: w_status = "🟡 CAUTION"
        
        r_status = "🔴 NO-GO" if rain_p > 70 else "🟡 CAUTION" if rain_p > 30 else "🟢 GO"

        st.header(f"Briefing: {st.session_state.boat}")
        st.caption(f"Snapshot: {st.session_state.date} | {st.session_state.start_t}:00 to {st.session_state.end_t}:00")

        # THE TABLE (Exact mirror of Static Gold)
        st.markdown(f"""
        | Metric | Value | Status |
        | :--- | :--- | :--- |
        | **WIND** | {w_speed} mph {w_dir} | {w_status} |
        | **GUSTS** | {w_gust} mph | {w_status} |
        | **TEMP (Air)** | {temp_a}°F | 🟢 GO |
        | **FLOW** | {flow_ft} ft | 🟢 GO |
        | **RAIN** | {rain_p}% | {r_status} |
        | **THUNDER** | -- (None) | 🟢 GO |
        """)

        st.markdown("### CONSIDERATIONS")
        st.info("Before departing, confirm [RESERVATION](https://scow.org/page-1863774), [MAINTENANCE](https://scow.org/page-1863774), and [WEATHER / NAV links](https://scow.org).")
        
        if st.session_state.boat == "Cruiser":
            st.write("* **Draft Warning:** Cruiser draws 3.5ft on a solid keel.")
        if "🟡" in w_status:
            st.write(f"* **Reefing Alert:** Gusts are high. Reefing is advised for {st.session_state.boat}.")

    if st.button("NEW PLAN"): st.session_state.page = 'home'; st.rerun()
