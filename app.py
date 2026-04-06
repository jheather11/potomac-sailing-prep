import re
from io import StringIO
from datetime import datetime, date, time, timedelta

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="Potomac Sail Prep (DCA)", layout="wide")

LAT = 38.8491
LON = -77.0438

# Official/structured sources used in this app:
# - NWS digital point forecast page (scraped to match the exact rows you are checking)
# - NOAA CO-OPS tides API, Washington DC station 8594900
# - USGS flow site 01646500 (Little Falls Pump Station), parameter 00060 discharge

NWS_DIGITAL_URL = (
    "https://forecast.weather.gov/MapClick.php"
    f"?w3=sfcwind&w3u=1&w13u=0&w16u=1&AheadHour=0&Submit=Submit"
    f"&FcstType=digital&textField1={LAT}&textField2={LON}&site=all&unit=0&dd=&bw="
)

NOAA_TIDES_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_TIDE_STATION = "8594900"  # Washington, DC

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
USGS_STAT_URL = "https://waterservices.usgs.gov/nwis/stat/"
USGS_SITE = "01646500"  # Potomac River near Wash, DC Little Falls Pump Sta


# -----------------------------
# HELPERS
# -----------------------------
HEADERS = {
    "User-Agent": "PotomacDCAForecast/1.0 (Streamlit app for SCOW planning)"
}


def safe_get(url: str, params=None, timeout: int = 25):
    resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def normalize_label(label: str) -> str:
    s = re.sub(r"\s+", " ", label).strip().lower()
    s = s.replace("°", "")
    return s


def parse_numeric_prefix(value):
    """
    Extracts leading numeric value from strings like:
    '14', '14 mph', '72', '2.5'
    Returns float or None.
    """
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def compact_wind_dir(seq):
    """
    Example:
      ['W','W','W','NW','NW','NW'] -> 'W-NW'
      ['NW'] -> 'NW'
    """
    seq = [clean_text(x) for x in seq if clean_text(x)]
    if not seq:
        return "--"
    unique_ordered = []
    for x in seq:
        if not unique_ordered or unique_ordered[-1] != x:
            unique_ordered.append(x)
    if len(unique_ordered) == 1:
        return unique_ordered[0]
    return f"{unique_ordered[0]}-{unique_ordered[-1]}"


def status_dot(status):
    return {
        "GO": "🟢 GO",
        "CAUTION": "🟡 CAUTION",
        "NO-GO": "🔴 NO-GO",
    }.get(status, status)


def format_time_12h(dt_obj):
    try:
        return dt_obj.strftime("%-I:%M %p")
    except Exception:
        # Windows fallback
        return dt_obj.strftime("%I:%M %p").lstrip("0")


# -----------------------------
# NWS DIGITAL TABLE PARSER
# -----------------------------
@st.cache_data(ttl=900, show_spinner=False)
def fetch_nws_digital_html():
    return safe_get(NWS_DIGITAL_URL).text


def extract_table_rows_from_html(html: str):
    """
    Reads all HTML tables and returns row lists from the digital forecast table(s).
    We intentionally scrape the same NWS digital page the user is checking manually.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    parsed_tables = []
    for table in tables:
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            row = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            row = [x for x in row if x != ""]
            if row:
                rows.append(row)

        if not rows:
            continue

        flat = " ".join(" ".join(r) for r in rows).lower()
        if "hour (edt)" in flat and "surface wind" in flat and "wind dir" in flat:
            parsed_tables.append(rows)

    return parsed_tables


def rows_to_hourly_dataframe(rows):
    """
    Converts one NWS digital table block into hourly records.

    Assumptions:
    - Each row is something like:
        ['Date', '04/05']
        ['Hour (EDT)', '13', '14', '15', ...]
        ['Temperature (°F)', '68', '67', ...]
        ['Surface Wind (mph)', '14', '9', ...]
        ['Wind Dir', 'W', 'W', ...]
        ['Gust', '21', '18', ...]
        ['Precipitation Potential (%)', '72', ...]
        ['Rain', 'Lkly', 'Chc', ...]
        ['Thunder', 'SChc', '--', ...]
    - If the hour rolls from 23 to 00, we advance the date by one day.
    """
    rowmap = {}
    for row in rows:
        label = normalize_label(row[0])
        values = row[1:]
        rowmap[label] = values

    if "hour (edt)" not in rowmap or "date" not in rowmap:
        return pd.DataFrame()

    date_tokens = rowmap.get("date", [])
    if not date_tokens:
        return pd.DataFrame()

    # Use the first date token as the starting date; if hours roll over, increment.
    start_date_token = date_tokens[0]
    try:
        start_month, start_day = map(int, start_date_token.split("/"))
        current_year = datetime.now().year
        current_date = date(current_year, start_month, start_day)
    except Exception:
        return pd.DataFrame()

    hours = rowmap["hour (edt)"]
    n = len(hours)

    def pick_row(*keys):
        for k in keys:
            if k in rowmap:
                vals = rowmap[k]
                if len(vals) < n:
                    vals = vals + [""] * (n - len(vals))
                return vals[:n]
        return [""] * n

    temperature = pick_row("temperature (f)", "temperature")
    wind = pick_row("surface wind (mph)", "surface wind")
    wind_dir = pick_row("wind dir")
    gust = pick_row("gust")
    pop = pick_row("precipitation potential (%)", "precipitation potential")
    rain = pick_row("rain")
    thunder = pick_row("thunder")

    records = []
    prev_hour = None
    dt_cursor = current_date

    for i, hr_str in enumerate(hours):
        hr_str = clean_text(hr_str)
        if not hr_str.isdigit():
            continue

        hour_num = int(hr_str)

        if prev_hour is not None and hour_num < prev_hour:
            dt_cursor = dt_cursor + timedelta(days=1)
        prev_hour = hour_num

        records.append(
            {
                "dt": datetime.combine(dt_cursor, time(hour=hour_num)),
                "temp_f": parse_numeric_prefix(temperature[i]),
                "wind_mph": parse_numeric_prefix(wind[i]),
                "wind_dir": clean_text(wind_dir[i]),
                "gust_mph": parse_numeric_prefix(gust[i]),
                "pop_pct": parse_numeric_prefix(pop[i]),
                "rain_code": clean_text(rain[i]),
                "thunder_code": clean_text(thunder[i]),
            }
        )

    return pd.DataFrame(records)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_nws_hourly_df():
    html = fetch_nws_digital_html()
    tables = extract_table_rows_from_html(html)

    dfs = []
    for rows in tables:
        df = rows_to_hourly_dataframe(rows)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        raise ValueError(
            "Could not parse the NWS digital table. "
            "The NWS page structure may have changed."
        )

    out = pd.concat(dfs, ignore_index=True)
    out = out.drop_duplicates(subset=["dt"]).sort_values("dt").reset_index(drop=True)
    return out


# -----------------------------
# NOAA TIDES
# -----------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_tides_for_day(selected_date: date):
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
        dt_obj = datetime.strptime(p["t"], "%Y-%m-%d %H:%M")
        rows.append(
            {
                "dt": dt_obj,
                "type": p.get("type", ""),
                "height_ft": float(p.get("v")),
            }
        )

    return pd.DataFrame(rows)


def summarize_tides(tides_df, start_dt, end_dt):
    if tides_df.empty:
        return "No tide data", "CAUTION"

    # Prefer events on the selected day, near the user's window
    after_start = tides_df[tides_df["dt"] >= start_dt]
    before_end = tides_df[tides_df["dt"] <= end_dt]

    next_high = after_start[after_start["type"].str.upper() == "H"].head(1)
    next_low = after_start[after_start["type"].str.upper() == "L"].head(1)

    if next_high.empty:
        next_high = tides_df[tides_df["type"].str.upper() == "H"].tail(1)
    if next_low.empty:
        next_low = tides_df[tides_df["type"].str.upper() == "L"].tail(1)

    parts = []
    if not next_high.empty:
        r = next_high.iloc[0]
        parts.append(f"High: ~{format_time_12h(r['dt'])} ({r['height_ft']:+.1f} ft)")
    if not next_low.empty:
        r = next_low.iloc[0]
        parts.append(f"Low: ~{format_time_12h(r['dt'])} ({r['height_ft']:+.1f} ft)")

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


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_usgs_annual_mean_flow():
    params = {
        "format": "rdb",
        "sites": USGS_SITE,
        "parameterCd": "00060",
        "statReportType": "annual",
    }
    text = safe_get(USGS_STAT_URL, params=params).text

    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(lines) < 2:
        return None

    df = pd.read_csv(StringIO("\n".join(lines)), sep="\t")
    # Keep only rows with year + mean
    df = df[df["mean_va"].notna()].copy()
    df["year_nu"] = pd.to_numeric(df["year_nu"], errors="coerce")
    df["mean_va"] = pd.to_numeric(df["mean_va"], errors="coerce")
    df = df.dropna(subset=["year_nu", "mean_va"]).sort_values("year_nu")

    if df.empty:
        return None

    # Use most recent available annual mean as the baseline
    return float(df.iloc[-1]["mean_va"])


def summarize_flow(current_cfs, avg_cfs):
    if current_cfs is None:
        return "No flow data", "CAUTION"

    avg_txt = f" (Avg: {avg_cfs:,.0f} cfs)" if avg_cfs is not None else ""

    if current_cfs >= 25000:
        status = "NO-GO"
    elif current_cfs >= 12000:
        status = "CAUTION"
    else:
        status = "GO"

    return f"Potomac (Little Falls): {current_cfs:,.0f} cfs{avg_txt}", status


# -----------------------------
# METRIC SUMMARIES
# -----------------------------
def summarize_weather_window(window_df):
    if window_df.empty:
        raise ValueError("No NWS weather rows found for the selected date/time window.")

    # Temperature
    temp_min = int(window_df["temp_f"].min()) if window_df["temp_f"].notna().any() else None
    temp_max = int(window_df["temp_f"].max()) if window_df["temp_f"].notna().any() else None
    temp_text = f"{temp_min}-{temp_max}°F" if temp_min is not None else "No data"

    if temp_max is None:
        temp_status = "CAUTION"
    elif temp_max < 45:
        temp_status = "CAUTION"
    else:
        temp_status = "GO"

    # Wind + Gusts
    wind_min = int(window_df["wind_mph"].min()) if window_df["wind_mph"].notna().any() else None
    wind_max = int(window_df["wind_mph"].max()) if window_df["wind_mph"].notna().any() else None
    gust_max = int(window_df["gust_mph"].max()) if window_df["gust_mph"].notna().any() else None
    wind_dir_text = compact_wind_dir(window_df["wind_dir"].tolist())

    if wind_min is not None and wind_max is not None:
        wind_range = f"{wind_min}-{wind_max} mph"
    elif wind_max is not None:
        wind_range = f"{wind_max} mph"
    else:
        wind_range = "No data"

    wind_text = f"{wind_range}, {wind_dir_text}"
    if gust_max is not None:
        wind_text += f", Gusts {gust_max} mph"

    if gust_max is None and wind_max is None:
        wind_status = "CAUTION"
    elif (gust_max or 0) >= 25 or (wind_max or 0) >= 18:
        wind_status = "NO-GO"
    elif (gust_max or 0) >= 18 or (wind_max or 0) >= 12:
        wind_status = "CAUTION"
    else:
        wind_status = "GO"

    # Rain / POP
    pop_max = int(window_df["pop_pct"].max()) if window_df["pop_pct"].notna().any() else None
    rain_codes = [x for x in window_df["rain_code"].tolist() if x and x != "--"]

    if rain_codes:
        rain_desc = " / ".join(pd.unique(rain_codes))
    else:
        rain_desc = "--"

    if pop_max is None:
        rain_text = "No rain data"
        rain_status = "CAUTION"
    else:
        rain_text = f"{rain_desc} ({pop_max}% max precip potential)"
        if pop_max >= 70:
            rain_status = "CAUTION"
        elif pop_max >= 30:
            rain_status = "CAUTION"
        else:
            rain_status = "GO"

    # Thunder - only from NWS Thunder row
    thunder_codes = [x for x in window_df["thunder_code"].tolist() if x and x != "--"]
    if thunder_codes:
        thunder_desc = " / ".join(pd.unique(thunder_codes))
        thunder_text = f"{thunder_desc} (thunder indicated by NWS digital row)"
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
# UI
# -----------------------------
st.title("⛵ Potomac Sail Prep (DCA)")
st.caption("SCOW planning dashboard using NWS digital forecast, NOAA tides, and USGS flow.")

craft = st.selectbox(
    "Select Your Craft",
    ["CRUISER - POTOMAC", "FLYING SCOTT - POTOMAC"],
    index=0,
)

with st.expander("Logistics checklist", expanded=True):
    a = st.checkbox("I have reviewed Maintenance Notes.")
    b = st.checkbox("I have confirmed my Reservation Slot.")
    c = st.checkbox("I have reviewed Weather/Nav links on the SCOW homepage.")

st.subheader("Float Plan")

col1, col2, col3 = st.columns(3)
with col1:
    selected_date = st.date_input("Select Date", value=date.today())
with col2:
    start_time = st.time_input("Start Time", value=time(hour=13, minute=0), step=3600)
with col3:
    end_time = st.time_input("End Time", value=time(hour=18, minute=0), step=3600)

if end_time <= start_time:
    st.error("End time must be later than start time.")
    st.stop()

run = st.button("GET FORECAST", type="primary")

if run:
    try:
        start_dt = datetime.combine(selected_date, start_time)
        end_dt = datetime.combine(selected_date, end_time)

        with st.spinner("Retrieving NWS / NOAA / USGS data..."):
            nws_df = fetch_nws_hourly_df()
            window_df = nws_df[(nws_df["dt"] >= start_dt) & (nws_df["dt"] <= end_dt)].copy()

            tides_df = fetch_tides_for_day(selected_date)
            current_flow = fetch_usgs_current_flow()
            avg_flow = fetch_usgs_annual_mean_flow()

        weather = summarize_weather_window(window_df)
        tide_text, tide_status = summarize_tides(tides_df, start_dt, end_dt)
        flow_text, flow_status = summarize_flow(current_flow, avg_flow)

        dashboard_rows = [
            {
                "Metric": "Wind/Gusts",
                "Value": weather["Wind/Gusts"][0],
                "Status": status_dot(weather["Wind/Gusts"][1]),
            },
            {
                "Metric": "Temp",
                "Value": weather["Temp"][0],
                "Status": status_dot(weather["Temp"][1]),
            },
            {
                "Metric": "Flow",
                "Value": flow_text,
                "Status": status_dot(flow_status),
            },
            {
                "Metric": "Tides",
                "Value": tide_text,
                "Status": status_dot(tide_status),
            },
            {
                "Metric": "Rain",
                "Value": weather["Rain"][0],
                "Status": status_dot(weather["Rain"][1]),
            },
            {
                "Metric": "Thunder",
                "Value": weather["Thunder"][0],
                "Status": status_dot(weather["Thunder"][1]),
            },
        ]

        all_statuses = [
            weather["Wind/Gusts"][1],
            weather["Temp"][1],
            flow_status,
            tide_status,
            weather["Rain"][1],
            weather["Thunder"][1],
        ]
        overall = overall_decision(all_statuses)

        st.subheader(f"Briefing: {craft.split(' - ')[0].title()}")
        st.write(
            f"**Date:** {selected_date.strftime('%Y-%m-%d')}  \n"
            f"**Window:** {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')} EDT  \n"
            f"**Overall:** {status_dot(overall)}"
        )

        dashboard_df = pd.DataFrame(dashboard_rows)
        st.dataframe(dashboard_df, use_container_width=True, hide_index=True)

        st.markdown("### Considerations")

        considerations = []

        if weather["Thunder"][1] == "NO-GO":
            considerations.append(
                "**General Safety:** NWS indicates thunder potential during the selected window. "
                "That should be treated as a no-go unless conditions clearly change."
            )

        if weather["Wind/Gusts"][1] == "NO-GO":
            considerations.append(
                "**Wind:** Wind and/or gusts are high enough to make conditions difficult and potentially unsafe."
            )
        elif weather["Wind/Gusts"][1] == "CAUTION":
            considerations.append(
                "**Wind:** Expect moderate breeze and/or gusts. Wider sections of the river may feel choppy."
            )

        if flow_status == "NO-GO":
            considerations.append(
                "**Flow:** River flow is very high at Little Falls. Treat downstream conditions with extra caution."
            )
        elif flow_status == "CAUTION":
            considerations.append(
                "**Flow:** Elevated flow may increase current strength and debris risk."
            )

        if weather["Rain"][1] == "CAUTION":
            considerations.append(
                "**Rain:** Periods of rain or showers may reduce comfort and visibility."
            )

        if not considerations:
            considerations.append("Conditions look generally favorable based on the selected metrics.")

        for item in considerations:
            st.markdown(f"- {item}")

        with st.expander("Hourly weather rows used for this briefing"):
            display_df = window_df.copy()
            display_df["dt"] = display_df["dt"].dt.strftime("%Y-%m-%d %H:%M")
            display_df = display_df.rename(
                columns={
                    "dt": "DateTime",
                    "temp_f": "Temp (F)",
                    "wind_mph": "Wind (mph)",
                    "wind_dir": "Wind Dir",
                    "gust_mph": "Gust (mph)",
                    "pop_pct": "POP (%)",
                    "rain_code": "Rain",
                    "thunder_code": "Thunder",
                }
            )
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Something broke while retrieving or parsing the data: {e}")
        st.info(
            "Most likely cause: the NWS digital page structure changed. "
            "If that happens, we can switch the weather section to the NWS API instead."
        )

st.markdown("---")
st.caption(
    "Sources: NWS digital point forecast (Reagan National point), NOAA CO-OPS tides, USGS Little Falls flow."
)
