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

HEADERS = {"User-Agent": "PotomacDCAForecast/1.0"}

TYPICAL_STAGE_FT = 3.5

# -----------------------------
# SESSION STATE
# -----------------------------
for key in ["slide", "craft", "forecast_rows", "overall_status", "briefing_meta"]:
    if key not in st.session_state:
        st.session_state[key] = None

if st.session_state.slide is None:
    st.session_state.slide = 1


# -----------------------------
# HELPERS
# -----------------------------
def safe_get(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r


def parse_iso(dt):
    return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(EASTERN_TZ).replace(tzinfo=None)


def status_dot(s):
    return {"GO": "🟢 GO", "CAUTION": "🟡 CAUTION", "NO-GO": "🔴 NO-GO"}[s]


def summarize_forecast_confidence(d):
    days = (d - datetime.now(EASTERN_TZ).date()).days
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
        low, high = map(int, re.findall(r"\d+", p["windSpeed"])) if re.findall(r"\d+", p["windSpeed"]) else (None, None)
        rows.append({
            "dt": parse_iso(p["startTime"]),
            "temp": p["temperature"],
            "wind_low": low,
            "wind_high": high,
            "dir": p["windDirection"]
        })
    return pd.DataFrame(rows)


# -----------------------------
# TIDES
# -----------------------------
@st.cache_data(ttl=1800)
def fetch_tides(d):
    params = {
        "product": "predictions",
        "application": "PotomacDCAForecast",
        "begin_date": d.strftime("%Y%m%d"),
        "end_date": d.strftime("%Y%m%d"),
        "datum": "MLLW",
        "station": NOAA_TIDE_STATION,
        "time_zone": "lst_ldt",
        "interval": "hilo",
        "units": "english",
        "format": "json",
    }
    data = safe_get(NOAA_TIDES_URL, params).json()
    return pd.DataFrame([{
        "dt": datetime.strptime(p["t"], "%Y-%m-%d %H:%M"),
        "type": p["type"],
        "h": float(p["v"])
    } for p in data["predictions"]])


def summarize_tides(df, start_dt, end_dt):
    df = df.sort_values("dt")
    dep = df[df.dt <= start_dt].tail(1)
    ret = df[df.dt > end_dt].head(1)

    def fmt(r):
        t = "H" if r["type"] == "H" else "L"
        return f"{t}: {r['dt'].strftime('%-I:%M %p')} ({r['h']:.1f} ft)"

    parts = []
    if not dep.empty:
        parts.append(fmt(dep.iloc[0]))
    if not ret.empty:
        parts.append(fmt(ret.iloc[0]))

    return " / ".join(parts), "GO"


# -----------------------------
# FLOW
# -----------------------------
@st.cache_data(ttl=900)
def fetch_stage():
    data = safe_get(USGS_IV_URL, {
        "format": "json",
        "sites": USGS_SITE,
        "parameterCd": "00065"
    }).json()

    return float(data["value"]["timeSeries"][0]["values"][0]["value"][-1]["value"])


def summarize_stage(stage):
    if stage >= 6:
        return f"{stage:.1f}ft (HIGH)", "NO-GO"
    if stage >= 4.5:
        return f"{stage:.1f}ft (elevated)", "CAUTION"
    if stage < 2.5:
        return f"{stage:.1f}ft (low)", "CAUTION"
    return f"{stage:.1f}ft (typical)", "GO"


# -----------------------------
# UI FLOW
# -----------------------------
if st.session_state.slide == 1:
    st.title("⛵ Potomac Sail Prep")
    if st.button("CRUISER - POTOMAC"):
        st.session_state.craft = "CRUISER"
        st.session_state.slide = 2
        st.rerun()

elif st.session_state.slide == 2:
    d = st.date_input("Date", date.today())
    s = st.time_input("Start", time(13))
    e = st.time_input("End", time(18))

    if st.button("GET FORECAST"):
        weather = fetch_weather()
        window = weather[(weather.dt >= datetime.combine(d, s)) & (weather.dt <= datetime.combine(d, e))]

        tides = fetch_tides(d)
        stage = fetch_stage()

        conf_txt, conf_status = summarize_forecast_confidence(d)
        tide_txt, tide_status = summarize_tides(tides, datetime.combine(d, s), datetime.combine(d, e))
        stage_txt, stage_status = summarize_stage(stage)

        rows = [
            {"Metric": "Data Confidence", "Value": conf_txt, "Status": status_dot(conf_status)},
            {"Metric": "Tides", "Value": tide_txt, "Status": status_dot(tide_status)},
            {"Metric": "Flow", "Value": stage_txt, "Status": status_dot(stage_status)},
        ]

        st.session_state.forecast_rows = rows
        st.session_state.overall_status = "GO"
        st.session_state.briefing_meta = {
            "weekday": d.strftime("%A"),
            "date": d.strftime("%Y-%m-%d"),
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

    st.markdown("---")
    st.markdown("### Share This Tool")

    st.markdown("[🔗 Open Site](https://potomac-dca-sailing-prep.streamlit.app/)")
    st.code("https://potomac-dca-sailing-prep.streamlit.app/")
