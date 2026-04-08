from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="centered")

# -----------------------------
# CONFIG
# -----------------------------
LAT = 38.8491
LON = -77.0438
EASTERN_TZ = ZoneInfo("America/New_York")

NOAA_TIDES_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_TIDE_STATION = "8594900"  # Washington, DC

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_SITE = "01646500"  # Little Falls

NDFD_XML_URL = "https://digital.weather.gov/xml/sample_products/browser_interface/ndfdXMLclient.php"

HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0"
}

# Static reference stage for operational comparison
TYPICAL_STAGE_FT = 3.5

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

if "debug_rows" not in st.session_state:
    st.session_state.debug_rows = None


# -----------------------------
# HELPERS
# -----------------------------
def safe_get(url, params=None, timeout=25):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def parse_iso_to_eastern_naive(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    dt_eastern = dt.astimezone(EASTERN_TZ)
    return dt_eastern.replace(tzinfo=None)


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


def extract_wind_range(wind_speed_raw):
    txt = str(wind_speed_raw or "").strip()
    nums = [int(x) for x in re.findall(r"\d+", txt)]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]
    return None, None


def infer_rain_bucket(short_forecast, detailed_forecast):
    txt = f"{short_forecast or ''} {detailed_forecast or ''}".lower()
    if "slight chance" in txt:
        return "SChc"
    if "likely" in txt:
        return "Likely"
    if "chance" in txt:
        return "Chc"
    if "showers" in txt or "rain" in txt:
        return "Rain"
    return "--"


def infer_thunder_flag(short_forecast, detailed_forecast):
    txt = f"{short_forecast or ''} {detailed_forecast or ''}".lower()
    terms = ["thunderstorm", "thunderstorms", "t-storm", "tstorms", "thunder"]
    return any(term in txt for term in terms)


def xml_localname(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_numeric(value):
    if value is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(value))
    return float(m.group(0)) if m else None


def summarize_forecast_confidence(selected_date):
    today_local = datetime.now(EASTERN_TZ).date()
    days_out = (selected_date - today_local).days

    if days_out <= 1:
        return "HIGH (reliable)", "GO"
    elif days_out <= 4:
        return "MEDIUM (check all forecasts day of sail)", "CAUTION"
    else:
        return "LOW (do not rely — recheck closer to sail time)", "CAUTION"


# -----------------------------
# NWS API WEATHER
# -----------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_nws_hourly_url(lat, lon):
    data = safe_get(f"https://api.weather.gov/points/{lat},{lon}").json()
    return data["properties"]["forecastHourly"]


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nws_hourly_dataframe(lat, lon):
    hourly_url = get_nws_hourly_url(lat, lon)
    data = safe_get(hourly_url).json()
    periods = data["properties"]["periods"]

    rows = []
    for p in periods:
        dt_obj = parse_iso_to_eastern_naive(p["startTime"])
        wind_low, wind_high = extract_wind_range(p.get("windSpeed"))

        rows.append(
            {
                "dt": dt_obj,
                "temp_f": p.get("temperature"),
                "wind_low_mph": wind_low,
                "wind_high_mph": wind_high,
                "wind_dir": p.get("windDirection"),
                "gust_mph": None,
                "pop_pct": p.get("probabilityOfPrecipitation", {}).get("value"),
                "rain_code": infer_rain_bucket(
                    p.get("shortForecast", ""),
                    p.get("detailedForecast", "")
                ),
                "thunder_code": "Thunder" if infer_thunder_flag(
                    p.get("shortForecast", ""),
                    p.get("detailedForecast", "")
                ) else "--",
                "short_forecast": p.get("shortForecast", ""),
                "detailed_forecast": p.get("detailedForecast", ""),
            }
        )

    return pd.DataFrame(rows).sort_values("dt").reset_index(drop=True)


# -----------------------------
# NDFD XML GUSTS
# -----------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_ndfd_gust_dataframe(lat, lon, start_dt, end_dt):
    params = {
        "lat": lat,
        "lon": lon,
        "product": "time-series",
        "begin": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "end": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "Unit": "e",
        "wgust": "wgust",
    }

    xml_text = safe_get(NDFD_XML_URL, params=params).text
    root = ET.fromstring(xml_text)

    time_layouts = {}
    for elem in root.iter():
        if xml_localname(elem.tag) == "time-layout":
            layout_key = None
            starts = []
            for child in elem:
                lname = xml_localname(child.tag)
                if lname == "layout-key":
                    layout_key = (child.text or "").strip()
                elif lname == "start-valid-time" and child.text:
                    starts.append(parse_iso_to_eastern_naive(child.text.strip()))
            if layout_key:
                time_layouts[layout_key] = starts

    gust_rows = []

    for elem in root.iter():
        lname = xml_localname(elem.tag)
        if lname != "wind-speed":
            continue

        elem_type = (elem.attrib.get("type") or "").strip().lower()
        name_text = ""
        layout_key = None
        values = []

        for child in elem:
            child_name = xml_localname(child.tag)
            if child_name == "name":
                name_text = (child.text or "").strip().lower()
            elif child_name == "time-layout":
                layout_key = (child.text or "").strip()
            elif child_name == "value":
                values.append(parse_numeric(child.text))

        is_gust = (elem_type == "gust") or ("gust" in name_text)
        if not is_gust or not layout_key or layout_key not in time_layouts:
            continue

        times = time_layouts[layout_key]
        for dt_obj, gust_val in zip(times, values):
            gust_rows.append({"dt": dt_obj, "gust_mph": gust_val})

    if not gust_rows:
        return pd.DataFrame(columns=["dt", "gust_mph"])

    df = pd.DataFrame(gust_rows)
    df = df.drop_duplicates(subset=["dt"]).sort_values("dt").reset_index(drop=True)
    return df


# -----------------------------
# NOAA TIDES
# -----------------------------
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


# -----------------------------
# USGS STAGE
# -----------------------------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_usgs_current_stage():
    params = {
        "format": "json",
        "sites": USGS_SITE,
        "parameterCd": "00065",  # gage height, feet
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
def summarize_tides(tides_df, start_dt, end_dt):
    if tides_df.empty:
        return "No tide data", "CAUTION", None

    tides_df = tides_df.sort_values("dt")

    before_start = tides_df[tides_df["dt"] <= start_dt].tail(1)
    after_start = tides_df[tides_df["dt"] > start_dt].head(1)
    after_end = tides_df[tides_df["dt"] > end_dt].head(1)

    def fmt_row(r):
        label = "High" if r["type"] == "H" else "Low"
        return f"{label} @ {fmt_ampm(r['dt'])} ({r['height_ft']:.1f} ft)"

    parts = []

    if not before_start.empty:
        parts.append(f"Departing: {fmt_row(before_start.iloc[0])}")

    if not after_start.empty:
        parts.append(f"Next: {fmt_row(after_start.iloc[0])}")

    if not after_end.empty:
        next_after_start_dt = after_start.iloc[0]["dt"] if not after_start.empty else None
        next_after_end_dt = after_end.iloc[0]["dt"]
        if next_after_start_dt is None or next_after_end_dt != next_after_start_dt:
            parts.append(f"Return: {fmt_row(after_end.iloc[0])}")

    tide_phase = None
    if not before_start.empty and not after_start.empty:
        prev_type = before_start.iloc[0]["type"]
        next_type = after_start.iloc[0]["type"]

        if prev_type == "H" and next_type == "L":
            tide_phase = "ebb"
        elif prev_type == "L" and next_type == "H":
            tide_phase = "flood"

    return "; ".join(parts), "GO", tide_phase


def summarize_stage(current_stage, tide_phase, typical_stage=TYPICAL_STAGE_FT):
    if current_stage is None:
        return "Potomac (Little Falls): No data", "CAUTION"

    flags = []

    if current_stage >= 6.0:
        status = "NO-GO"
    elif current_stage >= 4.5:
        status = "CAUTION"
        flags.append("High water")
    elif current_stage < 2.5:
        status = "CAUTION"
        if tide_phase == "ebb":
            flags.append("Low water + ebb")
        else:
            flags.append("Low water")
    else:
        status = "GO"

    text = f"Potomac (Little Falls): {current_stage:.1f}ft (typical={typical_stage:.1f})"
    if flags:
        text += f" | {' / '.join(flags)}"

    return text, status


def summarize_weather_window(window_df, craft):
    if window_df.empty:
        raise ValueError("No hourly forecast rows found for the selected date/time window.")

    # TEMP
    temp_min = int(window_df["temp_f"].min()) if window_df["temp_f"].notna().any() else None
    temp_max = int(window_df["temp_f"].max()) if window_df["temp_f"].notna().any() else None
    temp_text = range_text(temp_min, temp_max, "F")
    temp_status = "GO" if (temp_max is not None and temp_max >= 45) else "CAUTION"

    # WIND
    low_vals = window_df["wind_low_mph"].dropna().astype(int)
    high_vals = window_df["wind_high_mph"].dropna().astype(int)

    wind_min = int(low_vals.min()) if not low_vals.empty else None
    wind_max = int(high_vals.max()) if not high_vals.empty else None
    wind_dir_text = compact_wind_dir(window_df["wind_dir"].tolist())

    wind_text = f"{range_text(wind_min, wind_max, ' mph')}, {wind_dir_text}"
    wind_status = "CAUTION" if (wind_max is not None and wind_max >= 18) else "GO"

    # GUSTS
    gust_vals = window_df["gust_mph"].dropna()
    gust_max = int(gust_vals.max()) if not gust_vals.empty else None

    if gust_max is None:
        gust_text = "None Reported"
        gust_status = "GO"
    else:
        gust_text = f"{gust_max} mph"
        if craft == "CRUISER - POTOMAC":
            yellow_gust = 20
            red_gust = 29
        else:
            yellow_gust = 15
            red_gust = 19

        if gust_max >= red_gust:
            gust_status = "NO-GO"
        elif gust_max >= yellow_gust:
            gust_status = "CAUTION"
        else:
            gust_status = "GO"

    # RAIN
    pop_series = window_df["pop_pct"].dropna()
    pop_max = int(pop_series.max()) if not pop_series.empty else 0
    rain_desc = unique_join(window_df["rain_code"].tolist())

    if pop_max == 0 and rain_desc == "":
        rain_text = "None Reported"
        rain_status = "GO"
    elif pop_max == 0 and rain_desc in ("", "--"):
        rain_text = "None Reported"
        rain_status = "GO"
    else:
        rain_text = f"{rain_desc} ({pop_max}% max precip potential)" if rain_desc else f"{pop_max}% max precip potential"
        rain_status = "CAUTION" if pop_max >= 30 else "GO"

    # THUNDER
    thunder_present = any(
        str(x).strip() not in ("", "--") for x in window_df["thunder_code"].tolist()
    )
    if thunder_present:
        thunder_text = unique_join(window_df["thunder_code"].tolist())
        thunder_status = "NO-GO"
    else:
        thunder_text = "None Reported"
        thunder_status = "GO"

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
                        weather_df = fetch_nws_hourly_dataframe(LAT, LON)
                        gust_df = fetch_ndfd_gust_dataframe(LAT, LON, start_dt, end_dt)

                        if not gust_df.empty:
                            weather_df = weather_df.merge(gust_df, on="dt", how="left", suffixes=("", "_ndfd"))
                            if "gust_mph_ndfd" in weather_df.columns:
                                weather_df["gust_mph"] = weather_df["gust_mph_ndfd"]
                                weather_df = weather_df.drop(columns=["gust_mph_ndfd"])

                        window_df = weather_df[
                            (weather_df["dt"] >= start_dt) &
                            (weather_df["dt"] <= end_dt)
                        ].copy()

                        if window_df.empty:
                            raise ValueError(
                                "No hourly forecast rows found for that date/time window. Try a nearer date/time."
                            )

                        tides_df = fetch_tides_for_day(selected_date)
                        current_stage = fetch_usgs_current_stage()

                    confidence_text, confidence_status = summarize_forecast_confidence(selected_date)
                    weather = summarize_weather_window(window_df, st.session_state.craft)
                    tide_text, tide_status, tide_phase = summarize_tides(tides_df, start_dt, end_dt)
                    stage_text, stage_status = summarize_stage(current_stage, tide_phase)

                    rows = [
                        {"Metric": "Data Confidence", "Value": confidence_text, "Status": status_dot(confidence_status)},
                        {"Metric": "Wind", "Value": weather["Wind"][0], "Status": status_dot(weather["Wind"][1])},
                        {"Metric": "Gusts", "Value": weather["Gusts"][0], "Status": status_dot(weather["Gusts"][1])},
                        {"Metric": "Temp", "Value": weather["Temp"][0], "Status": status_dot(weather["Temp"][1])},
                        {"Metric": "Flow", "Value": stage_text, "Status": status_dot(stage_status)},
                        {"Metric": "Tides", "Value": tide_text, "Status": status_dot(tide_status)},
                        {"Metric": "Rain", "Value": weather["Rain"][0], "Status": status_dot(weather["Rain"][1])},
                        {"Metric": "Thunder", "Value": weather["Thunder"][0], "Status": status_dot(weather["Thunder"][1])},
                    ]

                    statuses = [
                        weather["Wind"][1],
                        weather["Gusts"][1],
                        weather["Temp"][1],
                        stage_status,
                        tide_status,
                        weather["Rain"][1],
                        weather["Thunder"][1],
                    ]
                    overall = overall_decision(statuses)

                    st.session_state.forecast_rows = rows
                    st.session_state.overall_status = overall
                    st.session_state.debug_rows = window_df.copy()
                    st.session_state.briefing_meta = {
                        "craft": st.session_state.craft,
                        "selected_date": selected_date.strftime("%Y-%m-%d"),
                        "selected_weekday": selected_date.strftime("%A"),
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
        f"**Date:** {meta.get('selected_weekday', '')}, {meta.get('selected_date', '')}  \n"
        f"**Window:** {meta.get('start_time', '')} to {meta.get('end_time', '')} EDT  \n"
        f"**Overall:** {status_dot(st.session_state.overall_status or 'GO')}"
    )

    df = pd.DataFrame(st.session_state.forecast_rows or [])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Considerations")

    notes = []
    row_lookup = {row["Metric"]: row for row in (st.session_state.forecast_rows or [])}

    confidence_value = row_lookup.get("Data Confidence", {}).get("Value", "")
    thunder_status = row_lookup.get("Thunder", {}).get("Status", "")
    wind_status = row_lookup.get("Wind", {}).get("Status", "")
    gust_status = row_lookup.get("Gusts", {}).get("Status", "")
    flow_status = row_lookup.get("Flow", {}).get("Status", "")
    flow_value = row_lookup.get("Flow", {}).get("Value", "")
    rain_status = row_lookup.get("Rain", {}).get("Status", "")

    if "MEDIUM" in confidence_value:
        notes.append("Data confidence is moderate — check all forecasts day of sail.")
    elif "LOW" in confidence_value:
        notes.append("Data confidence is low — do not rely on this forecast alone; recheck closer to sail time.")

    if "NO-GO" in thunder_status:
        notes.append("General Safety: Thunder appears in the selected forecast window.")

    if "NO-GO" in gust_status:
        notes.append("Gusts: Peak gusts are in the no-go range for this craft.")
    elif "CAUTION" in gust_status:
        notes.append("Gusts: Peak gusts are in the caution range for this craft.")

    if "CAUTION" in wind_status:
        notes.append("Wind: Sustained winds may still create chop, especially on wider river sections.")

    if "NO-GO" in flow_status:
        notes.append("River level: Little Falls stage is very high.")
    elif "CAUTION" in flow_status:
        if "Low water + ebb" in flow_value:
            notes.append("River level: Low water combined with ebb tide may increase grounding risk and make handling trickier in shallow areas.")
        elif "Low water" in flow_value:
            notes.append("River level: Low water may reduce depth margins in shallow areas.")
        else:
            notes.append("River level: Little Falls stage is elevated above typical easy conditions.")

    if "CAUTION" in rain_status:
        notes.append("Rain: Showers or elevated precipitation chances may reduce comfort and visibility.")

    if not notes:
        notes.append("Conditions look generally favorable across the selected metrics.")

    for note in notes:
        st.markdown(f"- {note}")

    with st.expander("Debug: hourly rows used"):
        dbg = st.session_state.debug_rows
        if dbg is not None and not dbg.empty:
            show = dbg.copy()
            show["dt"] = show["dt"].astype(str)
            st.dataframe(show, use_container_width=True, hide_index=True)

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
            st.session_state.debug_rows = None
            st.rerun()
