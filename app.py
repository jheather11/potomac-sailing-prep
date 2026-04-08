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
NOAA_TIDE_STATION = "8594900"

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_SITE = "01646500"

NDFD_XML_URL = "https://digital.weather.gov/xml/sample_products/browser_interface/ndfdXMLclient.php"

HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0"
}

TYPICAL_STAGE_FT = 3.5

# -----------------------------
# SESSION STATE
# -----------------------------
for key in ["slide", "craft", "forecast_rows", "overall_status", "briefing_meta", "debug_rows"]:
    if key not in st.session_state:
        st.session_state[key] = None

if st.session_state.slide is None:
    st.session_state.slide = 1


# -----------------------------
# HELPERS
# -----------------------------
def safe_get(url, params=None, timeout=25):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def parse_iso_to_eastern_naive(dt_str):
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.astimezone(EASTERN_TZ).replace(tzinfo=None)


def fmt_ampm(dt):
    try:
        return dt.strftime("%-I:%M %p")
    except:
        return dt.strftime("%I:%M %p").lstrip("0")


def status_dot(status):
    return {"GO": "🟢 GO", "CAUTION": "🟡 CAUTION", "NO-GO": "🔴 NO-GO"}.get(status, status)


def range_text(vmin, vmax, suffix=""):
    if vmin is None or vmax is None:
        return "No data"
    return f"{vmin}-{vmax}{suffix}" if vmin != vmax else f"{vmin}{suffix}"


def extract_wind_range(txt):
    nums = [int(x) for x in re.findall(r"\d+", str(txt))]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]
    return None, None


# -----------------------------
# DATA CONFIDENCE
# -----------------------------
def summarize_forecast_confidence(selected_date):
    today = datetime.now(EASTERN_TZ).date()
    days = (selected_date - today).days

    if days <= 1:
        return "HIGH (reliable)", "GO"
    elif days <= 4:
        return "MEDIUM (check all forecasts day of sail)", "CAUTION"
    else:
        return "LOW (do not rely — recheck closer to sail time)", "CAUTION"


# -----------------------------
# WEATHER
# -----------------------------
@st.cache_data(ttl=1800)
def fetch_weather():
    url = safe_get(f"https://api.weather.gov/points/{LAT},{LON}").json()["properties"]["forecastHourly"]
    periods = safe_get(url).json()["properties"]["periods"]

    rows = []
    for p in periods:
        dt = parse_iso_to_eastern_naive(p["startTime"])
        low, high = extract_wind_range(p.get("windSpeed"))
        rows.append({
            "dt": dt,
            "temp": p["temperature"],
            "wind_low": low,
            "wind_high": high,
            "wind_dir": p["windDirection"],
            "pop": p["probabilityOfPrecipitation"]["value"] or 0
        })
    return pd.DataFrame(rows)


# -----------------------------
# TIDES
# -----------------------------
@st.cache_data(ttl=1800)
def fetch_tides(d):
    params = {
        "product": "predictions",
        "begin_date": d.strftime("%Y%m%d"),
        "end_date": d.strftime("%Y%m%d"),
        "station": NOAA_TIDE_STATION,
        "interval": "hilo",
        "units": "english",
        "time_zone": "lst_ldt",
        "format": "json",
    }
    data = safe_get(NOAA_TIDES_URL, params=params).json()
    rows = []
    for p in data["predictions"]:
        rows.append({
            "dt": datetime.strptime(p["t"], "%Y-%m-%d %H:%M"),
            "type": p["type"],
            "h": float(p["v"])
        })
    return pd.DataFrame(rows)


def summarize_tides(df, start_dt, end_dt):
    df = df.sort_values("dt")

    before = df[df.dt <= start_dt].tail(1)
    after = df[df.dt > start_dt].head(1)
    ret = df[df.dt > end_dt].head(1)

    def fmt(r):
        t = "High" if r["type"] == "H" else "Low"
        return f"{t} @ {fmt_ampm(r['dt'])} ({r['h']:.1f} ft)"

    parts = []
    if not before.empty:
        parts.append(f"Departing: {fmt(before.iloc[0])}")
    if not after.empty:
        parts.append(f"Next: {fmt(after.iloc[0])}")
    if not ret.empty:
        parts.append(f"Return: {fmt(ret.iloc[0])}")

    phase = None
    if not before.empty and not after.empty:
        if before.iloc[0]["type"] == "H":
            phase = "ebb"
        else:
            phase = "flood"

    return "; ".join(parts), "GO", phase


# -----------------------------
# FLOW
# -----------------------------
@st.cache_data(ttl=900)
def fetch_stage():
    data = safe_get(USGS_IV_URL, params={
        "format": "json",
        "sites": USGS_SITE,
        "parameterCd": "00065"
    }).json()

    return float(data["value"]["timeSeries"][0]["values"][0]["value"][-1]["value"])


def summarize_stage(stage, phase):
    flags = []
    if stage >= 6:
        status = "NO-GO"
    elif stage >= 4.5:
        status = "CAUTION"
    elif stage < 2.5:
        status = "CAUTION"
        if phase == "ebb":
            flags.append("Low water + ebb")
    else:
        status = "GO"

    text = f"Potomac (Little Falls): {stage:.1f}ft (typical={TYPICAL_STAGE_FT})"
    if flags:
        text += " | " + ", ".join(flags)

    return text, status


# -----------------------------
# SLIDES
# -----------------------------
if st.session_state.slide == 1:
    st.title("⛵ Potomac Sail Prep")
    if st.button("CRUISER"):
        st.session_state.craft = "CRUISER"
        st.session_state.slide = 2
        st.rerun()

elif st.session_state.slide == 2:
    st.title("Float Plan")
    d = st.date_input("Date", date.today())
    s = st.time_input("Start", time(13))
    e = st.time_input("End", time(18))

    if st.button("GET FORECAST"):
        start_dt = datetime.combine(d, s)
        end_dt = datetime.combine(d, e)

        weather = fetch_weather()
        window = weather[(weather.dt >= start_dt) & (weather.dt <= end_dt)]

        tides = fetch_tides(d)
        stage = fetch_stage()

        conf_txt, conf_status = summarize_forecast_confidence(d)
        tide_txt, tide_status, phase = summarize_tides(tides, start_dt, end_dt)
        stage_txt, stage_status = summarize_stage(stage, phase)

        rows = [
            {"Metric": "Data Confidence", "Value": conf_txt, "Status": status_dot(conf_status)},
            {"Metric": "Flow", "Value": stage_txt, "Status": status_dot(stage_status)},
            {"Metric": "Tides", "Value": tide_txt, "Status": status_dot(tide_status)},
        ]

        st.session_state.forecast_rows = rows
        st.session_state.overall_status = "GO"
        st.session_state.briefing_meta = {
            "date": d.strftime("%Y-%m-%d"),
            "weekday": d.strftime("%A"),
            "start": s.strftime("%H:%M"),
            "end": e.strftime("%H:%M"),
        }

        st.session_state.slide = 3
        st.rerun()

elif st.session_state.slide == 3:
    m = st.session_state.briefing_meta

    st.title("Briefing")
    st.write(
        f"**Date:** {m['weekday']}, {m['date']}  \n"
        f"**Window:** {m['start']}–{m['end']} EDT  \n"
        f"**Overall:** {status_dot(st.session_state.overall_status)}"
    )

    st.dataframe(pd.DataFrame(st.session_state.forecast_rows), hide_index=True)
