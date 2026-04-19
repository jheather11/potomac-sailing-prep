from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import re
import html

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Potomac River SCOW Dashboard", layout="centered")

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

HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0"
}

TYPICAL_STAGE_FT = 3.5
SHARE_URL = "https://potomac-dca-sailing-prep.streamlit.app/"

DISCLAIMER_TEXT = (
    "Advisory only • Conditions change rapidly • "
    "Skipper responsible for vessel operation"
)

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


def summarize_forecast_confidence(selected_date):
    today_local = datetime.now(EASTERN_TZ).date()
    days_out = (selected_date - today_local).days

    if days_out <= 1:
        return "HIGH (reliable)", "GO"
    elif days_out <= 4:
        return "MEDIUM (check all forecasts day of sail)", "CAUTION"
    else:
        return "LOW (do not rely — recheck closer to sail time)", "CAUTION"


def days_out_from_today(selected_date):
    today_local = datetime.now(EASTERN_TZ).date()
    return (selected_date - today_local).days


def render_briefing_table(rows):
    def esc(text):
        return html.escape(str(text))

    table_rows = []
    for row in rows:
        table_rows.append(
            f"""
            <tr>
                <td class="psp-metric">{esc(row["Metric"])}</td>
                <td class="psp-value">{esc(row["Value"])}</td>
                <td class="psp-status">{esc(row["Status"])}</td>
            </tr>
            """
        )

    html_block = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
    body {{
        margin: 0;
        padding: 0;
        background: transparent;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .psp-table-wrap {{
        width: 100%;
        overflow-x: hidden;
        margin: 0;
        padding: 0;
    }}
    .psp-table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        table-layout: fixed;
        border: 1px solid rgba(128,128,128,0.28);
        border-radius: 16px;
        overflow: hidden;
        font-size: 15px;
        background: transparent;
    }}
    .psp-table th,
    .psp-table td {{
        padding: 10px 8px;
        border-bottom: 1px solid rgba(128,128,128,0.20);
        border-right: 1px solid rgba(128,128,128,0.18);
        vertical-align: top;
        text-align: left;
        word-break: break-word;
        overflow-wrap: anywhere;
        line-height: 1.25;
    }}
    .psp-table th:last-child,
    .psp-table td:last-child {{
        border-right: none;
    }}
    .psp-table tr:last-child td {{
        border-bottom: none;
    }}
    .psp-table thead th {{
        font-weight: 600;
        opacity: 0.85;
    }}
    .psp-metric {{
        width: 21%;
        font-weight: 600;
    }}
    .psp-value {{
        width: 55%;
    }}
    .psp-status {{
        width: 24%;
        white-space: nowrap;
        font-weight: 600;
    }}

    @media (max-width: 640px) {{
        .psp-table {{
            font-size: 13px;
        }}
        .psp-table th,
        .psp-table td {{
            padding: 8px 6px;
        }}
        .psp-metric {{
            width: 21%;
        }}
        .psp-value {{
            width: 51%;
        }}
        .psp-status {{
            width: 28%;
        }}
    }}
    </style>
    </head>
    <body>
        <div class="psp-table-wrap">
            <table class="psp-table">
                <thead>
                    <tr>
                        <th class="psp-metric">Metric</th>
                        <th class="psp-value">Value</th>
                        <th class="psp-status">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    height = 56 + (len(rows) * 48)
    components.html(html_block, height=height, scrolling=False)


def parse_iso8601_duration_to_hours(duration_text: str) -> float:
    """
    Minimal ISO8601 duration parser for strings like:
    PT1H, PT2H, PT30M, PT1H30M, P1DT6H
    """
    if not duration_text:
        return 1.0

    pattern = re.compile(
        r"^P"
        r"(?:(?P<days>\d+)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?"
        r")?$"
    )
    m = pattern.match(duration_text.strip())
    if not m:
        return 1.0

    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)

    total_hours = days * 24 + hours + minutes / 60 + seconds / 3600
    return total_hours if total_hours > 0 else 1.0


def kmh_to_mph(value):
    if value is None:
        return None
    return float(value) * 0.621371


def has_status(value, target):
    return target in str(value or "")


def extract_first_number(text):
    match = re.search(r"(-?\d+(?:\.\d+)?)", str(text or ""))
    return float(match.group(1)) if match else None


def get_direction_family(wind_value_text):
    txt = str(wind_value_text or "").upper()
    direction_tokens = [
        "NNE", "ENE", "ESE", "SSE", "SSW", "WSW", "WNW", "NNW",
        "NE", "SE", "SW", "NW",
        "N", "E", "S", "W",
    ]
    found = []
    for token in direction_tokens:
        if re.search(rf"\b{token}\b", txt):
            found.append(token)

    if not found:
        return None

    northerly = {"N", "NNE", "NNW", "NE", "NW"}
    southerly = {"S", "SSE", "SSW", "SE", "SW"}
    easterly = {"E", "ENE", "ESE", "NE", "SE"}
    westerly = {"W", "WNW", "WSW", "NW", "SW"}

    if any(token in northerly for token in found):
        return "N"
    if any(token in southerly for token in found):
        return "S"
    if any(token in easterly for token in found):
        return "E"
    if any(token in westerly for token in found):
        return "W"
    return found[0]


def build_considerations(rows, craft, overall_status):
    row_lookup = {row["Metric"]: row for row in rows}

    confidence_value = row_lookup.get("Data Confidence", {}).get("Value", "")
    wind_value = row_lookup.get("Wind", {}).get("Value", "")
    wind_status = row_lookup.get("Wind", {}).get("Status", "")
    gust_value = row_lookup.get("Gusts", {}).get("Value", "")
    gust_status = row_lookup.get("Gusts", {}).get("Status", "")
    temp_value = row_lookup.get("Temp", {}).get("Value", "")
    temp_status = row_lookup.get("Temp", {}).get("Status", "")
    flow_value = row_lookup.get("Flow", {}).get("Value", "")
    flow_status = row_lookup.get("Flow", {}).get("Status", "")
    rain_status = row_lookup.get("Rain", {}).get("Status", "")
    thunder_status = row_lookup.get("Thunder", {}).get("Status", "")

    notes = []

    wind_dir_family = get_direction_family(wind_value)
    tide_is_ebb = " / L:" in str(row_lookup.get("Tides", {}).get("Value", "")) or "ebb" in str(flow_value).lower()

    gust_mph = None if "None Reported" in str(gust_value) else extract_first_number(gust_value)
    wind_max = None
    wind_nums = [int(x) for x in re.findall(r"\d+", str(wind_value))]
    if wind_nums:
        wind_max = max(wind_nums)

    temp_min = None
    temp_nums = [int(x) for x in re.findall(r"\d+", str(temp_value))]
    if temp_nums:
        temp_min = min(temp_nums)

    flow_stage = extract_first_number(flow_value)

    def add_note(priority, text):
        notes.append({"priority": priority, "text": text})

    # -----------------------------
    # Highest priority
    # -----------------------------
    if has_status(thunder_status, "NO-GO"):
        add_note(100, "⚠️ Thunder risk present. Review radar and exit options.")

    if craft == "FLYING SCOT - POTOMAC":
        if has_status(gust_status, "NO-GO"):
            add_note(95, "⚠️ Strong gusts may increase heel / capsize risk.")
        elif has_status(gust_status, "CAUTION"):
            add_note(80, "⚠️ Gusts may require active sail management.")
    else:
        if has_status(gust_status, "NO-GO"):
            add_note(95, "⚠️ Strong gusts may complicate docking and control.")
        elif has_status(gust_status, "CAUTION"):
            add_note(80, "⚠️ Gusty conditions may affect close-quarters handling.")

    if has_status(rain_status, "CAUTION"):
        add_note(75, "⚠️ Reduced visibility may affect traffic awareness and docking.")

    # -----------------------------
    # Wind-based craft guidance
    # -----------------------------
    if craft == "FLYING SCOT - POTOMAC":
        if wind_max is not None and wind_max >= 15:
            add_note(78, "⚠️ Fresh breeze may favor reefing or reduced sail.")
        if wind_max is not None and wind_max >= 18:
            add_note(77, "⚠️ Reefing before departure may be easier than underway.")
    else:
        if wind_max is not None and wind_max >= 16:
            add_note(76, "⚠️ Fresh breeze may increase docking drift.")

    # -----------------------------
    # Temperature / immersion
    # -----------------------------
    if has_status(temp_status, "CAUTION") or (temp_min is not None and temp_min < 50):
        add_note(72, "⚠️ Cold conditions increase consequence of immersion.")

    # -----------------------------
    # Flow / tide / return trip
    # -----------------------------
    if has_status(flow_status, "NO-GO"):
        add_note(90, "⚠️ Elevated river level may increase maneuvering difficulty.")
    elif "Low water + ebb" in str(flow_value):
        if craft == "FLYING SCOT - POTOMAC":
            add_note(74, "⚠️ Low water and ebb may increase shallow-area risk near slips.")
        else:
            add_note(74, "⚠️ Low water may reduce margin outside marked channels.")
    elif "Low water" in str(flow_value):
        if craft == "FLYING SCOT - POTOMAC":
            add_note(70, "⚠️ Low water may increase shallow-area risk near slips.")
        else:
            add_note(70, "⚠️ Low water may reduce margin outside marked channels.")
    elif has_status(flow_status, "CAUTION"):
        add_note(69, "⚠️ River current may increase maneuvering difficulty.")

    if (
        wind_dir_family == "N"
        and tide_is_ebb
        and (
            (gust_mph is not None and gust_mph >= 15) or
            (wind_max is not None and wind_max >= 12)
        )
    ):
        add_note(73, "⚠️ Return trip may be slower against current and wind.")

    # -----------------------------
    # Craft-specific docking / launch handling
    # -----------------------------
    if craft == "FLYING SCOT - POTOMAC":
        if (
            (gust_mph is not None and gust_mph >= 15) or
            (wind_max is not None and wind_max >= 15)
        ):
            add_note(68, "⚠️ Launching or retrieval may require extra caution.")
    else:
        if (
            (gust_mph is not None and gust_mph >= 20) or
            (wind_max is not None and wind_max >= 16)
        ):
            add_note(68, "⚠️ Keelboat freeboard may increase sideways drift while docking.")

    # -----------------------------
    # Confidence
    # -----------------------------
    if "LOW" in str(confidence_value):
        add_note(60, "⚠️ Forecast confidence is lower. Recheck closer to departure.")
    elif "MEDIUM" in str(confidence_value) and overall_status != "NO-GO":
        add_note(55, "⚠️ Forecast confidence is moderate. Recheck day-of-sail.")

    # -----------------------------
    # Fallback GO language
    # -----------------------------
    if not notes:
        return ["✅ No significant operational concerns detected."]

    deduped = []
    seen = set()
    for item in sorted(notes, key=lambda x: x["priority"], reverse=True):
        text = item["text"]
        if text not in seen:
            deduped.append(text)
            seen.add(text)

    return deduped[:3]


# -----------------------------
# NWS API WEATHER
# -----------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_nws_point_data(lat, lon):
    return safe_get(f"https://api.weather.gov/points/{lat},{lon}").json()


@st.cache_data(ttl=3600, show_spinner=False)
def get_nws_hourly_url(lat, lon):
    data = get_nws_point_data(lat, lon)
    return data["properties"]["forecastHourly"]


@st.cache_data(ttl=3600, show_spinner=False)
def get_nws_grid_url(lat, lon):
    data = get_nws_point_data(lat, lon)
    return data["properties"]["forecastGridData"]


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


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nws_grid_gust_dataframe(lat, lon):
    """
    Pull gusts from forecastGridData, expand multi-hour validTime periods into
    hourly timestamps, and convert km/h to mph.
    """
    grid_url = get_nws_grid_url(lat, lon)
    data = safe_get(grid_url).json()
    props = data.get("properties", {})

    gust_block = props.get("windGust") or {}
    values = gust_block.get("values", [])

    rows = []
    for item in values:
        valid_time = item.get("validTime")
        value = item.get("value")

        if not valid_time or value is None:
            continue

        parts = valid_time.split("/")
        start_part = parts[0]
        duration_part = parts[1] if len(parts) > 1 else "PT1H"

        try:
            start_dt = parse_iso_to_eastern_naive(start_part)
        except Exception:
            continue

        total_hours = parse_iso8601_duration_to_hours(duration_part)
        hour_count = max(1, int(round(total_hours)))

        gust_mph = kmh_to_mph(value)
        if gust_mph is None:
            continue

        for i in range(hour_count):
            rows.append(
                {
                    "dt": start_dt + timedelta(hours=i),
                    "gust_mph": float(gust_mph),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["dt", "gust_mph"])

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["gust_mph"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["dt", "gust_mph"])

    df["dt"] = pd.to_datetime(df["dt"])
    df = (
        df.groupby("dt", as_index=False)["gust_mph"]
        .max()
        .sort_values("dt")
        .reset_index(drop=True)
    )
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
        "parameterCd": "00065",
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

    tides_df = tides_df.sort_values("dt").copy()

    def nearest_tide(df, target_dt):
        tmp = df.copy()
        tmp["delta_sec"] = (tmp["dt"] - target_dt).abs().dt.total_seconds()
        return tmp.sort_values(["delta_sec", "dt"]).iloc[0]

    dep_row = nearest_tide(tides_df, start_dt)
    ret_row = nearest_tide(tides_df, end_dt)

    before_start = tides_df[tides_df["dt"] <= start_dt].tail(1)
    after_start = tides_df[tides_df["dt"] > start_dt].head(1)

    tide_phase = None
    if not before_start.empty and not after_start.empty:
        prev_type = before_start.iloc[0]["type"]
        next_type = after_start.iloc[0]["type"]
        if prev_type == "H" and next_type == "L":
            tide_phase = "ebb"
        elif prev_type == "L" and next_type == "H":
            tide_phase = "flood"

    def fmt_row(r):
        label = "H" if r["type"] == "H" else "L"
        return f"{label}: {fmt_ampm(r['dt'])} ({r['height_ft']:.1f} ft)"

    tide_text = f"{fmt_row(dep_row)} / {fmt_row(ret_row)}"
    return tide_text, "GO", tide_phase


def summarize_stage(current_stage, tide_phase, selected_date, typical_stage=TYPICAL_STAGE_FT):
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

    if days_out_from_today(selected_date) >= 2:
        flags.append("check online")

    text = f"Potomac (Little Falls): {current_stage:.1f} ft (avg {typical_stage:.1f} ft)"
    if flags:
        text += f" | {' / '.join(flags)}"

    return text, status


def summarize_gusts_for_window(gust_df, start_dt, end_dt, craft):
    gust_max = None

    if gust_df is not None and not gust_df.empty:
        gust_window = gust_df[
            (gust_df["dt"] >= pd.Timestamp(start_dt)) &
            (gust_df["dt"] <= pd.Timestamp(end_dt))
        ].copy()

        if gust_window.empty:
            padded_start = start_dt - timedelta(minutes=60)
            padded_end = end_dt + timedelta(minutes=60)
            gust_window = gust_df[
                (gust_df["dt"] >= pd.Timestamp(padded_start)) &
                (gust_df["dt"] <= pd.Timestamp(padded_end))
            ].copy()

        if not gust_window.empty:
            gust_vals = pd.to_numeric(gust_window["gust_mph"], errors="coerce").dropna()
            if not gust_vals.empty:
                gust_max = int(round(gust_vals.max()))

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

    return gust_text, gust_status


def summarize_weather_window(window_df, craft, gust_df, start_dt, end_dt):
    if window_df.empty:
        raise ValueError("No hourly forecast rows found for the selected date/time window.")

    temp_min = int(window_df["temp_f"].min()) if window_df["temp_f"].notna().any() else None
    temp_max = int(window_df["temp_f"].max()) if window_df["temp_f"].notna().any() else None
    temp_text = range_text(temp_min, temp_max, "F")
    temp_status = "GO" if (temp_max is not None and temp_max >= 45) else "CAUTION"

    low_vals = window_df["wind_low_mph"].dropna().astype(int)
    high_vals = window_df["wind_high_mph"].dropna().astype(int)

    wind_min = int(low_vals.min()) if not low_vals.empty else None
    wind_max = int(high_vals.max()) if not high_vals.empty else None
    wind_dir_text = compact_wind_dir(window_df["wind_dir"].tolist())

    wind_text = f"{range_text(wind_min, wind_max, ' mph')}, {wind_dir_text}"
    wind_status = "CAUTION" if (wind_max is not None and wind_max >= 18) else "GO"

    gust_text, gust_status = summarize_gusts_for_window(gust_df, start_dt, end_dt, craft)

    pop_series = window_df["pop_pct"].dropna()
    pop_max = int(pop_series.max()) if not pop_series.empty else 0
    rain_desc = unique_join(window_df["rain_code"].tolist())

    if pop_max == 0 and rain_desc in ("", "--"):
        rain_text = "None Reported"
        rain_status = "GO"
    else:
        rain_text = f"{rain_desc} ({pop_max}% max precip potential)" if rain_desc else f"{pop_max}% max precip potential"
        rain_status = "CAUTION" if pop_max >= 30 else "GO"

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
.dashboard-disclaimer {
    font-size: 0.92rem;
    color: rgba(49, 51, 63, 0.78);
    margin-top: -0.45rem;
    margin-bottom: 1rem;
    line-height: 1.35;
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# SLIDE 1
# -----------------------------
if st.session_state.slide == 1:
    st.title("⛵ POTOMAC RIVER SCOW DASHBOARD")
    st.markdown(f'<div class="dashboard-disclaimer">{DISCLAIMER_TEXT}</div>', unsafe_allow_html=True)
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
    st.title("POTOMAC RIVER SCOW DASHBOARD")
    st.markdown(f'<div class="dashboard-disclaimer">{DISCLAIMER_TEXT}</div>', unsafe_allow_html=True)
    st.markdown(f"### Logistics: {st.session_state.craft.split(' - ')[0].title()}")
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
    st.title("POTOMAC RIVER SCOW DASHBOARD")
    st.markdown(f'<div class="dashboard-disclaimer">{DISCLAIMER_TEXT}</div>', unsafe_allow_html=True)
    st.markdown("### Float Plan")

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
                        gust_df = fetch_nws_grid_gust_dataframe(LAT, LON)

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
                    weather = summarize_weather_window(
                        window_df=window_df,
                        craft=st.session_state.craft,
                        gust_df=gust_df,
                        start_dt=start_dt,
                        end_dt=end_dt,
                    )
                    tide_text, tide_status, tide_phase = summarize_tides(tides_df, start_dt, end_dt)
                    stage_text, stage_status = summarize_stage(current_stage, tide_phase, selected_date)

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

                    try:
                        updated_text = datetime.now(EASTERN_TZ).strftime("%A, %Y-%m-%d, %-I:%M %p EDT")
                    except Exception:
                        updated_text = datetime.now(EASTERN_TZ).strftime("%A, %Y-%m-%d, %I:%M %p EDT").lstrip("0")

                    st.session_state.forecast_rows = rows
                    st.session_state.overall_status = overall
                    st.session_state.briefing_meta = {
                        "craft": st.session_state.craft,
                        "selected_date": selected_date.strftime("%Y-%m-%d"),
                        "selected_weekday": selected_date.strftime("%A"),
                        "start_time": start_time.strftime("%H:%M"),
                        "end_time": end_time.strftime("%H:%M"),
                        "updated_at": updated_text,
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

    st.title("POTOMAC RIVER SCOW DASHBOARD")
    st.markdown(f'<div class="dashboard-disclaimer">{DISCLAIMER_TEXT}</div>', unsafe_allow_html=True)
    st.markdown(f"### Briefing: {meta.get('craft', 'Craft').split(' - ')[0].title()}")
    st.write(
        f"**Date:** {meta.get('selected_weekday', '')}, {meta.get('selected_date', '')}  \n"
        f"**Window:** {meta.get('start_time', '')} to {meta.get('end_time', '')} EDT  \n"
        f"**Updated:** {meta.get('updated_at', '')}  \n"
        f"**Overall:** {status_dot(st.session_state.overall_status or 'GO')}"
    )

    rows = st.session_state.forecast_rows or []
    render_briefing_table(rows)

    st.markdown("### SCOW Considerations")

    notes = build_considerations(
        rows=rows,
        craft=meta.get("craft", st.session_state.craft or ""),
        overall_status=st.session_state.overall_status or "GO",
    )

    for note in notes:
        st.markdown(note)

    st.markdown("---")
    st.markdown("### Share This Tool")
    st.code(SHARE_URL, language="text")

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
