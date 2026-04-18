@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nws_gust_dataframe(lat, lon):
    """
    Fetch gust forecasts directly from NWS forecastGridData.
    This is the raw grid forecast endpoint and is more reliable than the
    older XML gust path for this app.
    """
    grid_url = get_nws_grid_url(lat, lon)
    data = safe_get(grid_url).json()

    props = data.get("properties", {})

    # Try common gust field names defensively
    gust_block = (
        props.get("windGust")
        or props.get("wind_gust")
        or props.get("gust")
        or {}
    )

    values = gust_block.get("values", [])
    rows = []

    for item in values:
        valid_time = item.get("validTime")
        value = item.get("value")

        if not valid_time or value is None:
            continue

        # validTime format example:
        # 2026-04-19T07:00:00+00:00/PT1H
        start_part = valid_time.split("/")[0]

        try:
            dt_obj = parse_iso_to_eastern_naive(start_part)
        except Exception:
            continue

        try:
            gust_val = float(value)
        except Exception:
            continue

        rows.append({"dt": dt_obj, "gust_mph": gust_val})

    if not rows:
        return pd.DataFrame(columns=["dt", "gust_mph"])

    df = pd.DataFrame(rows)
    df = (
        df.groupby("dt", as_index=False)["gust_mph"]
        .max()
        .sort_values("dt")
        .reset_index(drop=True)
    )
    return df
