from datetime import datetime, date, time, timedelta
import re

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="centered")

# -----------------------------
# CONFIG
# -----------------------------
LAT = 38.8491
LON = -77.0438

NWS_DIGITAL_URL = (
    "https://forecast.weather.gov/MapClick.php"
    "?w3=sfcwind&w3u=1&w13u=0&w16u=1&AheadHour=0&Submit=Submit"
    f"&FcstType=digital&textField1={LAT}&textField2={LON}&site=all&unit=0&dd=&bw="
)

NOAA_TIDES_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_TIDE_STATION = "8594900"  # Washington, DC

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_SITE = "01646500"  # Little Falls

HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0"
}

# -----------------------------
# SESSION STATE
# -----------------------------
if "slide" not in st.session_state:
    st.session_state.slide = 1

if "craft" not in st.session_state:
    st.session_state.craft = None

if "forecast_rows" not in st.session_state:
    st.session_state.forecast_rows = None

if "overall_status" not in st.session_state:
    st.session_state.overall_status = None

if "briefing_meta" not in st.session_state:
    st.session_state.briefing_meta = None


# -----------------------------
# HELPERS
# -----------------------------
def safe_get(url, params=None, timeout=25):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_label(label):
    s = clean_text(label).lower()
    s = s.replace("°", "")
    return s


def parse_numeric(value):
    if value is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(value))
    return float(m.group()) if m else None


def compact_wind_dir(seq):
    seq = [str(x).strip() for x in seq if str(x).strip()]
    if not seq:
        return "--"
    out = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    if len(out) == 1:
        return out[0]
    return f"{out[0]}-{out[-1]}"


def status_dot(status):
    return {
        "GO": "🟢 GO",
        "CAUTION": "🟡 CAUTION",
        "NO-GO": "🔴 NO-GO",
    }.get(status, status)


def fmt_ampm(dt_obj):
    try:
        return dt_obj.strftime("%-I:%M %p")
    except Exception:
        return dt_obj.strftime("%I:%M %p").lstrip("0")


def range_text(vmin, vmax, suffix=""):
    if vmin is None and vmax is None:
        return "No data"
    if vmin is None:
        return f"{vmax}{suffix}"
    if vmax is None:
        return f"{vmin}{suffix}"
    if vmin == vmax:
        return f"{vmin}{suffix}"
    return f"{vmin}-{vmax}{suffix}"


def unique_join(values):
    s = pd.Series(values, dtype="object")
    s = s.fillna("").astype(str).str.strip()
    s = s[s != ""]
    s = s[s != "--"]
    s = s.drop_duplicates()
    return " / ".join(s.tolist())


# -----------------------------
# DATA FETCHING
# -----------------------------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_nws_digital_dataframe():
    html = safe_get(NWS_DIGITAL_URL).text
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    target_rows = None

    for table in tables:
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            row = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            row = [x for x in row if x]
            if row:
                rows.append(row)

        flat = " ".join(" ".join(r) for r in rows).lower()
        if (
            "hour (edt)" in flat
            and "surface wind" in flat
            and "wind dir" in flat
            and "gust" in flat
        ):
            target_rows = rows
            break

    if not target_rows:
        raise ValueError("Could not find NWS digital forecast table.")

    rowmap = {}
    for row in target_rows:
        rowmap[normalize_label(row[0])] = row[1:]

    if "hour (edt)" not in rowmap or "date" not in rowmap:
        raise ValueError("NWS digital table missing Date or Hour rows.")

    hours = rowmap["hour (edt)"]
    date_vals = rowmap["date"]

    start_date_token = clean_text(date_vals[0])
    month, day = map(int, start_date_token.split("/"))
    year = datetime.now().year
    day_cursor = date(year, month, day)

    def get_row(*keys):
        for key in keys:
            if key in rowmap:
                vals = rowmap[key]
                if len(vals) < len(hours):
                    vals = vals + [""] * (len(hours) - len(vals))
                return vals[:len(hours)]
        return [""] * len(hours)

    temps = get_row("temperature (f)", "temperature")
    winds = get_row("surface wind (mph)", "surface wind")
    wind_dirs = get_row("wind dir")
    gusts = get_row("gust")
    pops = get_row("precipitation potential (%)", "precipitation potential")
    rain = get_row("rain")
    thunder = get_row("thunder")

    records = []
    prev_hour = None

    for i, hr in enumerate(hours):
        hr = clean_text(hr)
        if not hr.isdigit():
            continue

        hour_num = int(hr)

        if prev_hour is not None and hour_num < prev_hour:
            day_cursor = day_cursor + timedelta(days=1)
        prev_hour = hour_num

        records.append(
            {
                "dt": datetime.combine(day_cursor, time(hour=hour_num)),
                "temp_f": parse_numeric(temps[i]),
                "wind_mph": parse_numeric(winds[i]),
                "wind_dir": clean_text(wind_dirs[i]),
                "gust_mph": parse_numeric(gusts[i]),
                "pop_pct": parse_numeric(pops[i]),
                "rain_code": clean_text(rain[i]),
                "thunder_code": clean_text(thunder[i]),
            }
        )

    df = pd.DataFrame(records).sort_values("dt").reset_index(drop=True)
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_tides_for_day(selected_date):
    params = {
        "product": "predictions",
        "application": "PotomacDCAForecast",
        "begin_date": selected_date.strftime("%Y%m%d"),
        "end_date": selected_date.strftime("%Y%m%d"),
        "datum": "MLLW",
        "station": NOAA_TIDE_STATION,
        "time_zone": "lst_ldt",
        "interval": "hilo",
        "units": "english",
        "format": "json",
    }
    data = safe_get(NOAA_TIDES_URL, params=params).json()
    preds = data.get("predictions", [])

    rows = []
    for p in preds:
        rows.append(
            {
                "dt": datetime.strptime(p["t"], "%Y-%m-%d %H:%M"),
                "type": p["type"],
                "height_ft": float(p["v"]),
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_usgs_current_flow():
    params = {
        "format": "json",
        "sites": USGS_SITE,
        "parameterCd": "00060",
        "siteStatus": "all",
    }
    data = safe_get(USGS_IV_URL, params=params).json()
    series = data.get("value", {}).get("timeSeries", [])
    if not series:
        return None

    values = series[0].get("values", [])
    if not values or not values[0].get("value"):
        return None

    latest = values[0]["value"][-1]
    return float(latest["value"])


# -----------------------------
# SUMMARIES
# -----------------------------
def summarize_tides(tides_df, start_dt):
    if tides_df.empty:
        return "No tide data", "CAUTION"

    highs = tides_df[tides_df["type"] == "H"]
    lows = tides_df[tides_df["type"] == "L"]

    next_high = highs[highs["dt"] >= start_dt].head(1)
    next_low = lows[lows["dt"] >= start_dt].head(1)

    if next_high.empty and not highs.empty:
        next_high = highs.tail(1)
    if next_low.empty and not lows.empty:
        next_low = lows.tail(1)

    parts = []
    if not next_high.empty:
        r = next_high.iloc[0]
        parts.append(f"High: ~{fmt_ampm(r['dt'])} ({r['height_ft']:+.1f} ft)")
    if not next_low.empty:
        r = next_low.iloc[0]
        parts.append(f"Low: ~{fmt_ampm(r['dt'])} ({r['height_ft']:+.1f} ft)")

    return "; ".join(parts), "GO"


def summarize_flow(current_cfs):
    if current_cfs is None:
        return "No flow data", "CAUTION"

    if current_cfs >= 25000:
        status = "NO-GO"
    elif current_cfs >= 12000:
        status = "CAUTION"
    else:
        status = "GO"

    return f"Potomac (Little Falls): {current_cfs:,.0f} cfs", status


def summarize_weather_window(window_df, craft):
    if window_df.empty:
        raise ValueError("No hourly NWS forecast rows found for the selected date/time window.")

    temp_min = int(window_df["temp_f"].min()) if window_df["temp_f"].notna().any() else None
    temp_max = int(window_df["temp_f"].max()) if window_df["temp_f"].notna().any() else None
    temp_text = range_text(temp_min, temp_max, "F")
    temp_status = "GO" if (temp_max is not None and temp_max >= 45) else "CAUTION"

    wind_min = int(window_df["wind_mph"].min()) if window_df["wind_mph"].notna().any() else None
    wind_max = int(window_df["wind_mph"].max()) if window_df["wind_mph"].notna().any() else None
    gust_max = int(window_df["gust_mph"].max()) if window_df["gust_mph"].notna().any() else None
    wind_dir_text = compact_wind_dir(window_df["wind_dir"].tolist())

    wind_text = f"{range_text(wind_min, wind_max, ' mph')}, {wind_dir_text}"
    wind_status = "CAUTION" if (wind_max is not None and wind_max >= 18) else "GO"

    if craft == "CRUISER - POTOMAC":
        yellow_gust = 20
        red_gust = 29
    else:  # FLYING SCOT - POTOMAC
        yellow_gust = 15
        red_gust = 19

    gust_text = f"{gust_max} mph" if gust_max is not None else "No data"

    if gust_max is None:
        gust_status = "CAUTION"
    elif gust_max >= red_gust:
        gust_status = "NO-GO"
    elif gust_max >= yellow_gust:
        gust_status = "CAUTION"
    else:
        gust_status = "GO"

    pop_max = int(window_df["pop_pct"].max()) if window_df["pop_pct"].notna().any() else 0
    rain_desc = unique_join(window_df["rain_code"].tolist())
    rain_text = f"{rain_desc} ({pop_max}% max precip potential)" if rain_desc else f"{pop_max}% max precip potential"
    rain_status = "CAUTION" if pop_max >= 30 else "GO"

    thunder_present = any(
        str(x).strip() not in ("", "--") for x in window_df["thunder_code"].tolist()
    )
    thunder_text = unique_join(window_df["thunder_code"].tolist()) if thunder_present else "--"
    thunder_status = "NO-GO" if thunder_present else "GO"

    return {
        "Temp": (temp_text, temp_status),
        "Wind": (wind_text, wind_status),
        "Gusts": (gust_text, gust_status),
        "Rain": (rain_text, rain_status),
        "Thunder": (thunder_text, thunder_status),
    }


def overall_decision(statuses):
    if "NO-GO" in statuses:
        return "NO-GO"
    if "CAUTION" in statuses:
        return "CAUTION"
    return "GO"


# -----------------------------
# STYLING
# -----------------------------
st.markdown(
    """
<style>
div.stButton > button {
    width: 100%;
    border-radius: 8px;
    height: 3em;
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# SLIDE 1
# -----------------------------
if st.session_state.slide == 1:
    st.title("⛵ Potomac Sail Prep (DCA)")
    st.markdown("### Select Your Craft")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("FLYING SCOT - POTOMAC"):
            st.session_state.craft = "FLYING SCOT - POTOMAC"
            st.session_state.slide = 2
            st.rerun()
    with col2:
        if st.button("CRUISER - POTOMAC"):
            st.session_state.craft = "CRUISER - POTOMAC"
            st.session_state.slide = 2
            st.rerun()

    st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True)

# -----------------------------
# SLIDE 2
# -----------------------------
elif st.session_state.slide == 2:
    st.title(f"Logistics: {st.session_state.craft.split(' - ')[0].title()}")
    st.info("Check official SCOW sources before proceeding.")

    st.markdown(
        """
- [Maintenance Notes](https://www.scow.org/page-1863774)  
- [Reservation Slot](https://www.scow.org/page-1863774)  
- [Weather/Nav links](https://www.scow.org/) at the bottom of the SCOW homepage
"""
    )

    reviewed_maint = st.checkbox("I have reviewed Maintenance Notes (must sign in).")
    reviewed_slot = st.checkbox("I have confirmed my Reservation Slot.")
    reviewed_weather = st.checkbox("I have reviewed the Weather/Nav links at the bottom of the SCOW homepage.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("BACK"):
            st.session_state.slide = 1
            st.rerun()
    with col2:
        if st.button(
            "PROCEED TO FLOAT PLAN",
            disabled=not (reviewed_maint and reviewed_slot and reviewed_weather),
        ):
            st.session_state.slide = 3
            st.rerun()

# -----------------------------
# SLIDE 3
# -----------------------------
elif st.session_state.slide == 3:
    st.title("Float Plan")

    selected_date = st.date_input("Select Date", value=date.today())
    start_time = st.time_input("Start Time", value=time(13, 0), step=3600)
    end_time = st.time_input("End Time", value=time(18, 0), step=3600)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("BACK"):
            st.session_state.slide = 2
            st.rerun()
    with col2:
        if st.button("GET FORECAST", type="primary"):
            if end_time < start_time:
                st.error("End time must be later than or equal to start time.")
            else:
                try:
                    start_dt = datetime.combine(selected_date, start_time)
                    end_dt = datetime.combine(selected_date, end_time)

                    with st.spinner("Retrieving forecast data..."):
                        weather_df = fetch_nws_digital_dataframe()
                        window_df = weather_df[
                            (weather_df["dt"] >= start_dt) &
                            (weather_df["dt"] <= end_dt)
                        ].copy()

                        if window_df.empty:
                            raise ValueError(
                                "No hourly NWS forecast rows found for that date/time window."
                            )

                        tides_df = fetch_tides_for_day(selected_date)
                        current_flow = fetch_usgs_current_flow()

                    weather = summarize_weather_window(window_df, st.session_state.craft)
                    tide_text, tide_status = summarize_tides(tides_df, start_dt)
                    flow_text, flow_status = summarize_flow(current_flow)

                    rows = [
                        {"Metric": "Wind", "Value": weather["Wind"][0], "Status": status_dot(weather["Wind"][1])},
                        {"Metric": "Gusts", "Value": weather["Gusts"][0], "Status": status_dot(weather["Gusts"][1])},
                        {"Metric": "Temp", "Value": weather["Temp"][0], "Status": status_dot(weather["Temp"][1])},
                        {"Metric": "Flow", "Value": flow_text, "Status": status_dot(flow_status)},
                        {"Metric": "Tides", "Value": tide_text, "Status": status_dot(tide_status)},
                        {"Metric": "Rain", "Value": weather["Rain"][0], "Status": status_dot(weather["Rain"][1])},
                        {"Metric": "Thunder", "Value": weather["Thunder"][0], "Status": status_dot(weather["Thunder"][1])},
                    ]

                    statuses = [
                        weather["Wind"][1],
                        weather["Gusts"][1],
                        weather["Temp"][1],
                        flow_status,
                        tide_status,
                        weather["Rain"][1],
                        weather["Thunder"][1],
                    ]
                    overall = overall_decision(statuses)

                    st.session_state.forecast_rows = rows
                    st.session_state.overall_status = overall
                    st.session_state.briefing_meta = {
                        "craft": st.session_state.craft,
                        "selected_date": selected_date.strftime("%Y-%m-%d"),
                        "start_time": start_time.strftime("%H:%M"),
                        "end_time": end_time.strftime("%H:%M"),
                    }
                    st.session_state.slide = 4
                    st.rerun()

                except Exception as e:
                    st.error(f"GET FORECAST error: {e}")

# -----------------------------
# SLIDE 4
# -----------------------------
elif st.session_state.slide == 4:
    meta = st.session_state.briefing_meta or {}

    st.title(f"Briefing: {meta.get('craft', 'Craft').split(' - ')[0].title()}")
    st.write(
        f"**Date:** {meta.get('selected_date', '')}  \n"
        f"**Window:** {meta.get('start_time', '')} to {meta.get('end_time', '')} EDT  \n"
        f"**Overall:** {status_dot(st.session_state.overall_status or 'GO')}"
    )

    df = pd.DataFrame(st.session_state.forecast_rows or [])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Considerations")

    notes = []
    row_lookup = {row["Metric"]: row for row in (st.session_state.forecast_rows or [])}

    thunder_status = row_lookup.get("Thunder", {}).get("Status", "")
    wind_status = row_lookup.get("Wind", {}).get("Status", "")
    gust_status = row_lookup.get("Gusts", {}).get("Status", "")
    flow_status = row_lookup.get("Flow", {}).get("Status", "")
    rain_status = row_lookup.get("Rain", {}).get("Status", "")

    if "NO-GO" in thunder_status:
        notes.append("General Safety: Thunder appears in the selected forecast window.")

    if "NO-GO" in gust_status:
        notes.append("Gusts: Peak gusts are in the no-go range for this craft.")
    elif "CAUTION" in gust_status:
        notes.append("Gusts: Peak gusts are in the caution range for this craft.")

    if "CAUTION" in wind_status:
        notes.append("Wind: Sustained winds may still create chop, especially on wider river sections.")

    if "NO-GO" in flow_status:
        notes.append("Flow: River flow is very high.")
    elif "CAUTION" in flow_status:
        notes.append("Flow: Elevated river flow may increase current strength and debris risk.")

    if "CAUTION" in rain_status:
        notes.append("Rain: Showers or elevated precipitation chances may reduce comfort and visibility.")

    if not notes:
        notes.append("Conditions look generally favorable across the selected metrics.")

    for note in notes:
        st.markdown(f"- {note}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("BACK"):
            st.session_state.slide = 3
            st.rerun()
    with col2:
        if st.button("START OVER"):
            st.session_state.slide = 1
            st.session_state.craft = None
            st.session_state.forecast_rows = None
            st.session_state.overall_status = None
            st.session_state.briefing_meta = None
            st.rerun()
