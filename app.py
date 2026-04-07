@st.cache_data(ttl=1800, show_spinner=False)
def fetch_tides_for_day(selected_date):
    url = "https://tide.arthroinfo.org/tideshow.cgi"
    params = {
        "site": "Reagan National Airport, Washington, D.C.",
        "units": "f"
    }

    tables = pd.read_html(
        requests.get(url, params=params, headers=HEADERS, timeout=25).text
    )

    rows = []
    target_str = selected_date.strftime("%Y-%m-%d")

    for table in tables:
        for _, row in table.iterrows():
            row_text = " ".join(str(x) for x in row.tolist())
            if target_str in row_text and ("High Tide" in row_text or "Low Tide" in row_text):
                m = re.search(
                    r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+\w+\s+([-\d.]+)\s+feet\s+(High Tide|Low Tide)",
                    row_text
                )
                if m:
                    dt_obj = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
                    height = float(m.group(3))
                    tide_type = "H" if "High" in m.group(4) else "L"
                    rows.append({
                        "dt": dt_obj,
                        "type": tide_type,
                        "height_ft": height
                    })

    return pd.DataFrame(rows)
