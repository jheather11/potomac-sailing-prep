import math
import re
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# =========================
# CONFIG
# =========================
APP_TITLE = "⛵ Potomac Sail Prep (DCA)"
TIMEZONE = "America/New_York"
TZ = ZoneInfo(TIMEZONE)

# DCA area coordinates from your concept
LAT = 38.8491
LON = -77.0438

# Official data sources
NOAA_TIDE_STATION = "8594900"   # Washington, DC
USGS_FLOW_SITE = "01646500"     # Potomac River Near Wash, DC Little Falls Pump Sta

# Thresholds - edit these to match SCOW preferences
WIND_GO_MAX = 12
WIND_CAUTION_MAX = 18
GUST_GO_MAX = 18
GUST_CAUTION_MAX = 24

FLOW_GO_MAX = 12000
FLOW_CAUTION_MAX = 18000
FLOW_AVG_REFERENCE = 10000

RAIN_GO_MAX = 20
RAIN_CAUTION_MAX = 40

THUNDER_GO_MAX = 0
THUNDER_CAUTION_MAX = 10

AIR_TEMP_MIN_GO = 55
WATER_TEMP_MIN_GO = 52

REQUEST_HEADERS = {
    "User-Agent": "SCOW Potomac Sail Prep Dashboard (contact: replace-with-your-email@example.com)",
    "Accept": "application/geo+json, application/json"
}


# =========================
# HELPERS
# =========================
def fetch_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    hdrs = REQUEST_HEADERS.copy()
    if headers:
        hdrs.update(headers)
    r = requests.get(url, params=params, headers=hdrs, timeout=30)
    r.raise_for_status()
    return r.json()


def normalize_ws_value(ws_str: str | None) -> float | None:
    """
    Convert NWS windSpeed text like '10 mph' or '10 to 15 mph' to a numeric midpoint.
    """
    if not ws_str:
        return None
    nums = [int(x) for x in re.findall(r"\d+", ws_str)]
    if not nums:
        return None
    if len(nums) == 1:
        return float(nums[0])
    return float(sum(nums[:2]) / 2)


def mph_to_knots(mph: float | None) -> float | None:
    if mph is None:
        return None
    return mph * 0.868976


def c_to_f(c: float | None) -> float | None:
    if c is None:
        return None
    return (c * 9 / 5) + 32


def parse_iso_to_local(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.astimezone(TZ)


def format_kts(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{round(value):.0f} kts"


def format_pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    return f"{round(value):.0f}%"


def format_temp_range(min_v: float | None, max_v: float | None) -> str:
    if min_v is None or max_v is None or math.isnan(min_v) or math.isnan(max_v):
        return "N/A"
    if round(min_v) == round(max_v):
        return f"{round(min_v):.0f}°F"
    return f"{round(min_v):.0f}-{round(max_v):.0f}°F"


def status_badge(status: str) -> str:
    if status == "GO":
        return "🟢 GO"
    if status == "CAUTION":
        return "🟡 CAUTION"
    return "🔴 NO-GO"


def worst_status(statuses: list[str]) -> str:
    if "NO-GO" in statuses:
        return "NO-GO"
    if "CAUTION" in statuses:
        return "CAUTION"
    return "GO"


def start_end_datetimes(selected_date: date, start_str: str, end_str: str) -> tuple[datetime, datetime]:
    start_hour, start_min = map(int, start_str.split(":"))
    end_hour, end_min = map(int, end_str.split(":"))

    start_dt = datetime.combine(selected_date, time(start_hour, start_min), tzinfo=TZ)
    end_dt = datetime.combine(selected_date, time(end_hour, end_min), tzinfo=TZ)

    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


# =========================
# DATA FETCHERS
# =========================
@st.cache_data(ttl=900, show_spinner=False)
def get_nws_hourly_forecast(lat: float, lon: float) -> pd.DataFrame:
    """
    Uses api.weather.gov points -> forecastHourly
    """
    points = fetch_json(f"https://api.weather.gov/points/{lat},{lon}")
    hourly_url = points["properties"]["forecastHourly"]

    data = fetch_json(hourly_url)
    periods = data["properties"]["periods"]

    rows = []
    for p in periods:
        dt_local = parse_iso_to_local(p["startTime"])
        wind_mph = normalize_ws_value(p.get("windSpeed"))
        wind_kts = mph_to_knots(wind_mph)

        rows.append({
            "time": dt_local,
            "temperature_f": float(p["temperature"]) if p.get("temperature") is not None else None,
            "wind_kts": wind_kts,
            "wind_direction": p.get("windDirection"),
            "rain_pct": float(p.get("probabilityOfPrecipitation", {}).get("value") or 0),
            "short_forecast": p.get("shortForecast", ""),
            "detailed_forecast": p.get("detailedForecast", ""),
            # gusts are not reliably separate in this endpoint; we estimate from phrases if present below
            "raw_wind_speed": p.get("windSpeed", "")
        })

    df = pd.DataFrame(rows)
    df["gust_kts"] = df.apply(estimate_gust_from_forecast_row, axis=1)
    df["thunder_pct"] = df.apply(estimate_thunder_probability, axis=1)
    return df.sort_values("time").reset_index(drop=True)


def estimate_gust_from_forecast_row(row) -> float | None:
    """
    Try to infer gusts from forecast text.
    If the text explicitly mentions gusts, use the highest number found near 'gust'.
    Otherwise use a conservative multiplier from sustained wind.
    """
    text = f"{row.get('short_forecast', '')} {row.get('detailed_forecast', '')}"
    matches = re.findall(r"gusts?\s+(?:up to\s+)?(\d+)\s?mph", text, flags=re.I)
    if matches:
        gust_mph = max(int(x) for x in matches)
        return mph_to_knots(float(gust_mph))

    wind_kts = row.get("wind_kts")
    if wind_kts is None or pd.isna(wind_kts):
        return None

    # fallback estimate
    return wind_kts * 1.3


@st.cache_data(ttl=1800, show_spinner=False)
def get_noaa_tides(selected_date: date) -> pd.DataFrame:
    """
    HILO predictions for the selected date from NOAA CO-OPS.
    """
    begin_date = selected_date.strftime("%Y%m%d")
    end_date = (selected_date + timedelta(days=1)).strftime("%Y%m%d")

    params = {
        "product": "predictions",
        "application": "scow_dashboard",
        "begin_date": begin_date,
        "end_date": end_date,
        "datum": "MLLW",
        "station": NOAA_TIDE_STATION,
        "time_zone": "lst_ldt",
        "interval": "hilo",
        "units": "english",
        "format": "json"
    }

    data = fetch_json("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", params=params)
    preds = data.get("predictions", [])

    rows = []
    for p in preds:
        dt_local = datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        rows.append({
            "time": dt_local,
            "height_ft": float(p["v"]),
            "type": p["type"]  # H or L
        })

    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def get_usgs_flow_latest() -> dict:
    """
    Current discharge for Little Falls.
    Parameter 00060 = discharge (cfs)
    """
    params = {
        "format": "json",
        "sites": USGS_FLOW_SITE,
        "parameterCd": "00060",
        "siteStatus": "all"
    }

    data = fetch_json("https://waterservices.usgs.gov/nwis/iv/", params=params)
    series = data["value"]["timeSeries"]
    if not series:
        return {"flow_cfs": None, "observed_at": None}

    values = series[0]["values"][0]["value"]
    if not values:
        return {"flow_cfs": None, "observed_at": None}

    latest = values[-1]
    observed_at = parse_iso_to_local(latest["dateTime"])
    flow_cfs = float(latest["value"])

    return {"flow_cfs": flow_cfs, "observed_at": observed_at}


def estimate_water_temp_from_air_range(min_air_f: float | None, max_air_f: float | None) -> tuple[float | None, float | None]:
    """
    Placeholder because your current source list does not include a live water temp feed.
    Replace later with a real water-temp station if desired.
    """
    if min_air_f is None or max_air_f is None:
        return None, None

    avg_air = (min_air_f + max_air_f) / 2
    est_water = max(42, min(78, avg_air - 8))
    return est_water - 2, est_water + 2


# =========================
# BUSINESS LOGIC
# =========================
def status_for_wind(avg_wind_kts: float | None, max_gust_kts: float | None) -> str:
    checks = []

    if avg_wind_kts is not None and not math.isnan(avg_wind_kts):
        if avg_wind_kts > WIND_CAUTION_MAX:
            checks.append("NO-GO")
        elif avg_wind_kts > WIND_GO_MAX:
            checks.append("CAUTION")
        else:
            checks.append("GO")

    if max_gust_kts is not None and not math.isnan(max_gust_kts):
        if max_gust_kts > GUST_CAUTION_MAX:
            checks.append("NO-GO")
        elif max_gust_kts > GUST_GO_MAX:
            checks.append("CAUTION")
        else:
            checks.append("GO")

    return worst_status(checks) if checks else "CAUTION"


def status_for_flow(flow_cfs: float | None) -> str:
    if flow_cfs is None or math.isnan(flow_cfs):
        return "CAUTION"
    if flow_cfs > FLOW_CAUTION_MAX:
        return "NO-GO"
    if flow_cfs > FLOW_GO_MAX:
        return "CAUTION"
    return "GO"


def status_for_rain(max_rain_pct: float | None) -> str:
    if max_rain_pct is None or math.isnan(max_rain_pct):
        return "GO"
    if max_rain_pct > RAIN_CAUTION_MAX:
        return "NO-GO"
    if max_rain_pct > RAIN_GO_MAX:
        return "CAUTION"
    return "GO"


def status_for_thunder(max_thunder_pct: float | None) -> str:
    if max_thunder_pct is None or math.isnan(max_thunder_pct):
        return "GO"
    if max_thunder_pct > THUNDER_CAUTION_MAX:
        return "NO-GO"
    if max_thunder_pct > THUNDER_GO_MAX:
        return "CAUTION"
    return "GO"


def status_for_temp(min_air_f: float | None, min_water_f: float | None) -> str:
    checks = []
    if min_air_f is not None and not math.isnan(min_air_f):
        if min_air_f < AIR_TEMP_MIN_GO:
            checks.append("CAUTION")
        else:
            checks.append("GO")
    if min_water_f is not None and not math.isnan(min_water_f):
        if min_water_f < WATER_TEMP_MIN_GO:
            checks.append("CAUTION")
        else:
            checks.append("GO")
    return worst_status(checks) if checks else "CAUTION"


def summarize_wind_direction(series: pd.Series) -> str:
    mode = series.mode()
    if len(mode) > 0:
        return str(mode.iloc[0])
    return "Variable"


def estimate_thunder_probability(row) -> float:
    """
    NWS hourly endpoint does not consistently expose thunder % as a dedicated hourly field.
    So this uses a practical heuristic:
    - If thunderstorm language appears, use at least the rain probability.
    - Otherwise 0.
    """
    text = f"{row.get('short_forecast', '')} {row.get('detailed_forecast', '')}".lower()
    rain_pct = float(row.get("rain_pct") or 0)

    thunder_words = [
        "thunderstorm", "t-storm", "tstorm", "storms", "lightning", "thunder"
    ]
    if any(word in text for word in thunder_words):
        return max(10.0, rain_pct)
    return 0.0


def build_considerations(metrics: dict) -> list[str]:
    notes = []

    if metrics["thunder_status"] == "NO-GO":
        notes.append(
            "General Safety: Thunderstorm or lightning risk makes water-based activity not recommended. "
            "Monitor official alerts closely."
        )

    if metrics["wind_status"] in ["CAUTION", "NO-GO"]:
        notes.append(
            f"Wind: Sustained winds around {format_kts(metrics['avg_wind_kts'])} with gusts to "
            f"{format_kts(metrics['max_gust_kts'])} may create choppy conditions, especially on wider reaches."
        )

    if metrics["flow_status"] in ["CAUTION", "NO-GO"]:
        notes.append(
            f"Flow: Potomac at Little Falls is running about {metrics['flow_cfs']:,.0f} cfs "
            f"(reference avg: {FLOW_AVG_REFERENCE:,.0f} cfs), which may increase current-related challenges."
        )

    if metrics["temp_status"] == "CAUTION":
        notes.append(
            "Temperature: Cooler air or water temperatures can increase exposure risk. Dress for immersion, not air alone."
        )

    if metrics["rain_status"] == "CAUTION":
        notes.append(
            "Rain: Periodic showers may reduce comfort and visibility; verify radar before departure."
        )
    elif metrics["rain_status"] == "NO-GO":
        notes.append(
            "Rain: Higher precipitation chances suggest a less favorable sail window."
        )

    if not notes:
        notes.append("Conditions appear generally favorable for the selected window. Continue normal pre-sail checks.")

    return notes


# =========================
# UI
# =========================
st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="wide")

if "step" not in st.session_state:
    st.session_state.step = 1
if "craft" not in st.session_state:
    st.session_state.craft = None
if "forecast_ready" not in st.session_state:
    st.session_state.forecast_ready = False
if "metrics" not in st.session_state:
    st.session_state.metrics = None
if "window_start" not in st.session_state:
    st.session_state.window_start = None
if "window_end" not in st.session_state:
    st.session_state.window_end = None
if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()


st.title(APP_TITLE)

with st.expander("Official Sources", expanded=False):
    st.markdown(
        """
- Weather: National Weather Service hourly forecast API
- Tides: NOAA CO-OPS Washington, DC station
- Flow: USGS Little Falls Pump Station
        """
    )


def go_to_step(step_num: int):
    st.session_state.step = step_num


# -------------------------
# STEP 1 - Craft
# -------------------------
if st.session_state.step == 1:
    st.subheader("Select Your Craft")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("FLYING SCOTT - POTOMAC", use_container_width=True):
            st.session_state.craft = "Flying Scott - Potomac"
            go_to_step(2)
    with col2:
        if st.button("CRUISER - POTOMAC", use_container_width=True):
            st.session_state.craft = "Cruiser - Potomac"
            go_to_step(2)
    with col3:
        st.button("CRUISER - ANNAPOLIS (BETA)", disabled=True, use_container_width=True)


# -------------------------
# STEP 2 - Logistics
# -------------------------
elif st.session_state.step == 2:
    st.subheader(f"Logistics: {st.session_state.craft.split(' - ')[0]}")

    st.info("Check official SCOW sources before proceeding.")

    reviewed_maintenance = st.checkbox("I have reviewed Maintenance Notes.")
    confirmed_slot = st.checkbox("I have confirmed my Reservation Slot.")
    reviewed_links = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")

    ready = reviewed_maintenance and confirmed_slot and reviewed_links

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("BACK"):
            go_to_step(1)
    with col2:
        if st.button("PROCEED TO FLOAT PLAN", disabled=not ready):
            go_to_step(3)


# -------------------------
# STEP 3 - Float Plan
# -------------------------
elif st.session_state.step == 3:
    st.subheader("Float Plan")

    selected_date = st.date_input("Select Date", value=st.session_state.selected_date)
    start_str = st.selectbox(
        "Start Time",
        options=[f"{h:02d}:00" for h in range(0, 24)],
        index=13
    )
    end_str = st.selectbox(
        "End Time",
        options=[f"{h:02d}:00" for h in range(0, 24)],
        index=18
    )

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("BACK"):
            go_to_step(2)
    with c2:
        if st.button("GET FORECAST", type="primary"):
            st.session_state.selected_date = selected_date
            st.session_state.window_start, st.session_state.window_end = start_end_datetimes(
                selected_date, start_str, end_str
            )

            with st.spinner("Retrieving weather, tides, and flow..."):
                hourly = get_nws_hourly_forecast(LAT, LON)
                tides = get_noaa_tides(selected_date)
                flow = get_usgs_flow_latest()

            window_df = hourly[
                (hourly["time"] >= st.session_state.window_start) &
                (hourly["time"] <= st.session_state.window_end)
            ].copy()

            if window_df.empty:
                st.error("No forecast data was returned for that time window.")
            else:
                avg_wind_kts = window_df["wind_kts"].mean()
                max_gust_kts = window_df["gust_kts"].max()
                min_air_f = window_df["temperature_f"].min()
                max_air_f = window_df["temperature_f"].max()
                max_rain_pct = window_df["rain_pct"].max()
                max_thunder_pct = window_df["thunder_pct"].max()
                wind_dir = summarize_wind_direction(window_df["wind_direction"])

                water_low_f, water_high_f = estimate_water_temp_from_air_range(min_air_f, max_air_f)

                tide_window = tides[
                    (tides["time"] >= datetime.combine(selected_date, time.min, tzinfo=TZ)) &
                    (tides["time"] < datetime.combine(selected_date + timedelta(days=1), time.min, tzinfo=TZ))
                ].copy()

                high_tides = tide_window[tide_window["type"] == "H"]
                low_tides = tide_window[tide_window["type"] == "L"]

                next_high = high_tides.iloc[0].to_dict() if not high_tides.empty else None
                next_low = low_tides.iloc[0].to_dict() if not low_tides.empty else None

                wind_status = status_for_wind(avg_wind_kts, max_gust_kts)
                temp_status = status_for_temp(min_air_f, water_low_f)
                flow_status = status_for_flow(flow["flow_cfs"])
                rain_status = status_for_rain(max_rain_pct)
                thunder_status = status_for_thunder(max_thunder_pct)

                tide_status = "GO"  # Placeholder; tide itself is informative, not inherently unsafe
                overall_status = worst_status([
                    wind_status, temp_status, flow_status, tide_status, rain_status, thunder_status
                ])

                st.session_state.metrics = {
                    "avg_wind_kts": avg_wind_kts,
                    "max_gust_kts": max_gust_kts,
                    "wind_dir": wind_dir,
                    "min_air_f": min_air_f,
                    "max_air_f": max_air_f,
                    "min_water_f": water_low_f,
                    "max_water_f": water_high_f,
                    "flow_cfs": flow["flow_cfs"],
                    "flow_observed_at": flow["observed_at"],
                    "next_high": next_high,
                    "next_low": next_low,
                    "max_rain_pct": max_rain_pct,
                    "max_thunder_pct": max_thunder_pct,
                    "wind_status": wind_status,
                    "temp_status": temp_status,
                    "flow_status": flow_status,
                    "tide_status": tide_status,
                    "rain_status": rain_status,
                    "thunder_status": thunder_status,
                    "overall_status": overall_status,
                    "window_df": window_df
                }

                st.session_state.forecast_ready = True
                go_to_step(4)


# -------------------------
# STEP 4 - Briefing
# -------------------------
elif st.session_state.step == 4:
    m = st.session_state.metrics
    selected_date = st.session_state.selected_date
    start_dt = st.session_state.window_start
    end_dt = st.session_state.window_end

    st.subheader(f"Briefing: {st.session_state.craft.split(' - ')[0]}")

    st.caption(
        f"Date: {selected_date.isoformat()} | "
        f"Window: {start_dt.strftime('%H:%M')} to {end_dt.strftime('%H:%M')} | "
        f"Overall: {status_badge(m['overall_status'])}"
    )

    wind_value = (
        f"{m['wind_dir']} {round(m['avg_wind_kts']):.0f} kts, Gusts to {round(m['max_gust_kts']):.0f} kts"
        if m["avg_wind_kts"] is not None and m["max_gust_kts"] is not None
        else "N/A"
    )

    temp_value = (
        f"Air: {format_temp_range(m['min_air_f'], m['max_air_f'])}; "
        f"Water: {format_temp_range(m['min_water_f'], m['max_water_f'])} (estimated)"
    )

    flow_value = (
        f"Potomac (Little Falls): {m['flow_cfs']:,.0f} cfs (Avg: {FLOW_AVG_REFERENCE:,.0f} cfs)"
        if m["flow_cfs"] is not None else "N/A"
    )

    if m["next_high"] and m["next_low"]:
        tides_value = (
            f"High: ~{m['next_high']['time'].strftime('%H:%M %Z')} "
            f"({m['next_high']['height_ft']:+.1f} ft); "
            f"Low: ~{m['next_low']['time'].strftime('%H:%M %Z')} "
            f"({m['next_low']['height_ft']:+.1f} ft)"
        )
    else:
        tides_value = "N/A"

    rain_value = f"Max precip chance during window: {format_pct(m['max_rain_pct'])}"
    thunder_value = f"Max thunder risk during window: {format_pct(m['max_thunder_pct'])}"

    table_df = pd.DataFrame([
        {"Metric": "Wind/Gusts", "Value": wind_value, "Status": status_badge(m["wind_status"])},
        {"Metric": "Temp", "Value": temp_value, "Status": status_badge(m["temp_status"])},
        {"Metric": "Flow", "Value": flow_value, "Status": status_badge(m["flow_status"])},
        {"Metric": "Tides", "Value": tides_value, "Status": status_badge(m["tide_status"])},
        {"Metric": "Rain", "Value": rain_value, "Status": status_badge(m["rain_status"])},
        {"Metric": "Thunder", "Value": thunder_value, "Status": status_badge(m["thunder_status"])},
    ])

    st.dataframe(table_df, use_container_width=True, hide_index=True)

    st.markdown("**Considerations:**")
    for note in build_considerations(m):
        st.markdown(f"- {note}")

    with st.expander("Hourly Detail"):
        detail = m["window_df"].copy()
        detail["time"] = detail["time"].dt.strftime("%Y-%m-%d %H:%M")
        detail = detail.rename(columns={
            "time": "Time",
            "temperature_f": "Air Temp (°F)",
            "wind_kts": "Wind (kts)",
            "gust_kts": "Gust (kts)",
            "wind_direction": "Dir",
            "rain_pct": "Rain %",
            "thunder_pct": "Thunder %",
            "short_forecast": "Forecast"
        })
        detail = detail[["Time", "Air Temp (°F)", "Wind (kts)", "Gust (kts)", "Dir", "Rain %", "Thunder %", "Forecast"]]
        st.dataframe(detail, use_container_width=True, hide_index=True)

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("BACK"):
            go_to_step(3)
    with c2:
        if st.button("START OVER"):
            st.session_state.step = 1
            st.session_state.forecast_ready = False
            st.session_state.metrics = None
            st.rerun()
