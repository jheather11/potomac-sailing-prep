from datetime import datetime, date, time, timedelta
import re

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="wide")

# -----------------------------
# CONFIG
# -----------------------------
LAT = 38.8491
LON = -77.0438

NOAA_TIDES_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_TIDE_STATION = "8594900"  # Washington, DC

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_SITE = "01646500"  # Little Falls

HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0 contact: SCOW dashboard"
}

# -----------------------------
# HELPERS
# -----------------------------
def safe_get(url, params=None, timeout=25):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def parse_iso_z(dt_str):
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


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


def mph_to_int(v):
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except Exception:
        return None


def extract_thunder_flag(short_forecast, detailed_forecast):
    txt = f"{short_forecast or ''} {detailed_forecast or ''}".lower()
    thunder_terms = [
        "thunderstorm",
        "thunderstorms",
        "slight chance of thunderstorms",
        "chance of thunderstorms",
        "t-storm",
        "tstorm",
    ]
    return any(term in txt for term in thunder_terms)


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


# -----------------------------
# NWS HOURLY FORECAST API
# -----------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_nws_hourly_url(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    data = safe_get(url).json()
    return data["properties"]["forecastHourly"]


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nws_hourly_dataframe(lat, lon):
    hourly_url = get_nws_hourly_url(lat, lon)
    data = safe_get(hourly_url).json()
    periods = data["properties"]["periods"]

    rows = []
    for p in periods:
        dt_obj = parse_iso_z(p["startTime"])

        wind_speed_raw = str(p.get("windSpeed", "")).strip()
        # examples: "9 mph", "10 to 15 mph"
        nums = [int(x) for x in re.findall(r"\d+", wind_speed_raw)]
        if len(nums) >= 2:
            wind_low, wind_high = nums[0], nums[1]
        elif len(nums) == 1:
            wind_low = wind_high = nums[0]
        else:
            wind_low = wind_high = None

        gust = p.get("windGust")
        gust_mph = mph_to_int(gust)

        rows.append({
            "dt": dt_obj,
            "temp_f": p.get("temperature"),
            "wind_low_mph": wind_low,
            "wind_high_mph": wind_high,
            "wind_dir": p.get("windDirection"),
            "gust_mph": gust_mph,
            "short_forecast": p.get("shortForecast", ""),
            "detailed_forecast": p.get("detailedForecast", ""),
            "precip_prob": p.get("probabilityOfPrecipitation", {}).get("value"),
            "is_daytime": p.get("isDaytime"),
            "thunder_flag": extract_thunder_flag(
                p.get("shortForecast", ""),
                p.get("detailedForecast", "")
            )
        })

    df = pd.DataFrame(rows).sort_values("dt").reset_index(drop=True)
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
        rows.append({
            "dt": datetime.strptime(p["t"], "%Y-%m-%d %H:%M"),
            "type": p["type"],
            "height_ft": float(p["v"]),
        })
    return pd.DataFrame(rows)


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


# -----------------------------
# USGS FLOW
# -----------------------------
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


# -----------------------------
# WEATHER SUMMARY
# -----------------------------
def summarize_weather_window(window_df):
    if window_df.empty:
        raise ValueError("No hourly NWS forecast rows found for the selected date/time window.")

    # temp
    temp_min = int(window_df["temp_f"].min()) if window_df["temp_f"].notna().any() else None
    temp_max = int(window_df["temp_f"].max()) if window_df["temp_f"].notna().any() else None
    temp_text = f"{range_text(temp_min, temp_max, '°F')}"
    temp_status = "GO" if (temp_max is not None and temp_max >= 45) else "CAUTION"

    # wind
    low_vals = window_df["wind_low_mph"].dropna().astype(int)
    high_vals = window_df["wind_high_mph"].dropna().astype(int)
    gust_vals = window_df["gust_mph"].dropna().astype(int)

    wind_min = int(low_vals.min()) if not low_vals.empty else None
    wind_max = int(high_vals.max()) if not high_vals.empty else None
    gust_max = int(gust_vals.max()) if not gust_vals.empty else None
    wind_dir_text = compact_wind_dir(window_df["wind_dir"].tolist())

    wind_text = f"{range_text(wind_min, wind_max, ' mph')}, {wind_dir_text}"
    if gust_max is not None:
        wind_text += f", Gusts {gust_max} mph"

    if gust_max is not None and gust_max >= 25:
        wind_status = "NO-GO"
    elif wind_max is not None and wind_max >= 18:
        wind_status = "CAUTION"
    elif gust_max is not None and gust_max >= 18:
        wind_status = "CAUTION"
    else:
        wind_status = "GO"

    # rain
    precip_vals = window_df["precip_prob"].dropna()
    precip_max = int(precip_vals.max()) if not precip_vals.empty else 0

    shorts = " / ".join(pd.unique(window_df["short_forecast"].fillna("").tolist()))
    rain_text = f"{shorts} ({precip_max}% max precip potential)" if shorts.strip() else f"{precip_max}% max precip potential"

    if precip_max >= 30:
        rain_status = "CAUTION"
    else:
        rain_status = "GO"

    # thunder
    thunder_present = bool(window_df["thunder_flag"].any())
    if thunder_present:
        thunder_text = "Thunder mentioned in NWS hourly forecast"
        thunder_status = "NO-GO"
    else:
        thunder_text = "--"
        thunder_status = "GO"

    return {
        "Temp": (temp_text, temp_status),
        "Wind/Gusts": (wind_text, wind_status),
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
# APP LAYOUT
# -----------------------------
st.title("⛵ Potomac Sail Prep (DCA)")

st.markdown("## 1. Select Your Craft")
craft = st.selectbox(
    "Craft",
    ["CRUISER - POTOMAC", "FLYING SCOTT - POTOMAC", "CRUISER - ANNAPOLIS (BETA)"],
    index=0
)

st.markdown("## 2. Logistics")
st.info("Check official SCOW sources before proceeding.")

st.markdown(
    """
- Review **Maintenance Notes**
- Confirm your **Reservation Slot**
- Review **Weather/Nav links** on the SCOW homepage
"""
)

check1 = st.checkbox("I have reviewed Maintenance Notes.")
check2 = st.checkbox("I have confirmed my Reservation Slot.")
check3 = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")

gate_open = check1 and check2 and check3

st.markdown("## 3. Float Plan")

if not gate_open:
    st.warning("Complete all three logistics checks to unlock the float plan.")
    st.stop()

col1, col2, col3 = st.columns(3)
with col1:
    selected_date = st.date_input("Select Date", value=date.today())
with col2:
    start_time = st.time_input("Start Time", value=time(13, 0), step=3600)
with col3:
    end_time = st.time_input("End Time", value=time(18, 0), step=3600)

if end_time <= start_time:
    st.error("End time must be later than start time.")
    st.stop()

if st.button("GET FORECAST", type="primary"):
    try:
        start_dt = datetime.combine(selected_date, start_time)
        end_dt = datetime.combine(selected_date, end_time)

        with st.spinner("Retrieving forecast data..."):
            weather_df = fetch_nws_hourly_dataframe(LAT, LON)
            window_df = weather_df[(weather_df["dt"] >= start_dt) & (weather_df["dt"] <= end_dt)].copy()

            if window_df.empty:
                raise ValueError(
                    "No hourly NWS forecast rows found for that date/time window. "
                    "Try a nearer date; NWS hourly forecast usually covers only the upcoming forecast horizon."
                )

            tides_df = fetch_tides_for_day(selected_date)
            current_flow = fetch_usgs_current_flow()

        weather = summarize_weather_window(window_df)
        tide_text, tide_status = summarize_tides(tides_df, start_dt)
        flow_text, flow_status = summarize_flow(current_flow)

        rows = [
            {"Metric": "Wind/Gusts", "Value": weather["Wind/Gusts"][0], "Status": status_dot(weather["Wind/Gusts"][1])},
            {"Metric": "Temp", "Value": weather["Temp"][0], "Status": status_dot(weather["Temp"][1])},
            {"Metric": "Flow", "Value": flow_text, "Status": status_dot(flow_status)},
            {"Metric": "Tides", "Value": tide_text, "Status": status_dot(tide_status)},
            {"Metric": "Rain", "Value": weather["Rain"][0], "Status": status_dot(weather["Rain"][1])},
            {"Metric": "Thunder", "Value": weather["Thunder"][0], "Status": status_dot(weather["Thunder"][1])},
        ]

        statuses = [
            weather["Wind/Gusts"][1],
            weather["Temp"][1],
            flow_status,
            tide_status,
            weather["Rain"][1],
            weather["Thunder"][1],
        ]
        overall = overall_decision(statuses)

        st.markdown("## 4. Briefing")
        st.write(
            f"**Craft:** {craft}  \n"
            f"**Date:** {selected_date.strftime('%Y-%m-%d')}  \n"
            f"**Window:** {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')} EDT  \n"
            f"**Overall:** {status_dot(overall)}"
        )

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("### Considerations")
        notes = []

        if weather["Thunder"][1] == "NO-GO":
            notes.append("General Safety: Thunder appears in the official NWS hourly forecast during the selected window.")

        if weather["Wind/Gusts"][1] == "NO-GO":
            notes.append("Wind: Gusts are high enough to make conditions potentially unsafe.")
        elif weather["Wind/Gusts"][1] == "CAUTION":
            notes.append("Wind: Moderate winds or gusts may create choppy conditions, especially on wider sections.")

        if flow_status == "CAUTION":
            notes.append("Flow: Elevated river flow may increase current strength and debris risk.")
        elif flow_status == "NO-GO":
            notes.append("Flow: River flow is very high. Proceed only with extreme caution.")

        if weather["Rain"][1] == "CAUTION":
            notes.append("Rain: Showers or elevated precipitation chances may reduce comfort and visibility.")

        if not notes:
            notes.append("Conditions look generally favorable across the selected metrics.")

        for n in notes:
            st.markdown(f"- {n}")

        with st.expander("Hourly forecast rows used"):
            show_df = window_df.copy()
            show_df["dt"] = show_df["dt"].dt.strftime("%Y-%m-%d %H:%M")
            show_df = show_df.rename(columns={
                "dt": "DateTime",
                "temp_f": "Temp (F)",
                "wind_low_mph": "Wind Low",
                "wind_high_mph": "Wind High",
                "wind_dir": "Wind Dir",
                "gust_mph": "Gust (mph)",
                "precip_prob": "POP (%)",
                "short_forecast": "Short Forecast",
                "thunder_flag": "Thunder Flag",
            })
            st.dataframe(show_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"GET FORECAST error: {e}")
