"""Prepare the real 2015 Greenpoint 311 record for the offline sandbox."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "data" / "Original"
PROCESSED = ROOT / "data" / "Processed"

NOISE_FILE = ORIGINAL / "greenpoint_noise_2015.json"
BOUNDARY_FILE = ORIGINAL / "zip11222.geojson"
OUTPUT_FILE = PROCESSED / "greenpoint_noise_processed.json"
TEMPLATE_FILE = ROOT / "work" / "index_template.html"
INDEX_FILE = ROOT / "index.html"

CATEGORY_NAMES = {
    "Noise - Residential": "Residential",
    "Noise": "Unspecified noise",
    "Noise - Commercial": "Commercial",
    "Noise - Street/Sidewalk": "Street / sidewalk",
    "Noise - Vehicle": "Vehicle",
    "Noise - Park": "Park",
    "Noise - House of Worship": "Other",
    "Noise - Helicopter": "Other",
}


def iter_dates(start: date, end: date):
    """Yield every calendar date, including dates with zero source rows."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    # 1. Read the original files without changing them.
    rows = json.loads(NOISE_FILE.read_text())
    boundary = json.loads(BOUNDARY_FILE.read_text())
    frame = pd.DataFrame(rows)
    print(f"1. Original 311 rows: {len(frame):,}")
    print(f"   Boundary features: {len(boundary.get('features', [])):,}")

    # 2. Parse the fields used by the model and check required values.
    frame["created_date"] = pd.to_datetime(frame["created_date"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    required = ["unique_key", "created_date", "complaint_type", "latitude", "longitude"]
    missing = frame[required].isna().any(axis=1)
    print(f"2. Rows missing a required field: {int(missing.sum()):,}")
    if missing.any():
        print(frame.loc[missing, required].to_string(index=False))
    frame = frame.loc[~missing].copy()
    print(f"   Rows retained: {len(frame):,}")

    # 3. Keep the 2015 ZIP 11222 record used in Assignment 2 and 3.
    in_scope = (
        (frame["created_date"].dt.year == 2015)
        & (frame["incident_zip"].astype(str) == "11222")
    )
    fallen_out = frame.loc[~in_scope]
    print(f"3. Rows outside 2015 or ZIP 11222: {len(fallen_out):,}")
    frame = frame.loc[in_scope].copy()
    print(f"   Rows retained: {len(frame):,}")

    # 4. Use six named categories and preserve the three rare source rows as Other.
    frame["category"] = frame["complaint_type"].map(CATEGORY_NAMES)
    unknown = frame["category"].isna()
    print(f"4. Rows with an unmapped complaint type: {int(unknown.sum()):,}")
    if unknown.any():
        print(frame.loc[unknown, "complaint_type"].value_counts().to_string())
        frame.loc[unknown, "category"] = "Other"
    print(f"   Rows retained: {len(frame):,}")

    # 5. Derive date, weekday, minute-of-day and night labels from each source time.
    frame["date"] = frame["created_date"].dt.strftime("%Y-%m-%d")
    frame["weekday"] = frame["created_date"].dt.dayofweek
    frame["minute"] = frame["created_date"].dt.hour * 60 + frame["created_date"].dt.minute
    frame["night_22_03"] = (
        (frame["created_date"].dt.hour >= 22) | (frame["created_date"].dt.hour < 3)
    )
    print(f"5. Derived fields added; rows retained: {len(frame):,}")

    # 6. Make one compact row per real 311 request for the browser.
    compact_rows = []
    for row in frame.itertuples(index=False):
        compact_rows.append(
            [
                str(row.unique_key),
                row.date,
                int(row.weekday),
                int(row.minute),
                row.category,
                round(float(row.latitude), 6),
                round(float(row.longitude), 6),
            ]
        )
    print(f"6. Compact browser rows: {len(compact_rows):,}")

    # 7. Include every day of 2015 so zero-request days remain possible in resampling.
    all_days = [d.isoformat() for d in iter_dates(date(2015, 1, 1), date(2015, 12, 31))]
    observed_days = set(frame["date"])
    zero_days = [d for d in all_days if d not in observed_days]
    print(f"7. Calendar days included: {len(all_days):,}")
    print(f"   Zero-request days retained: {len(zero_days):,}")

    # 8. Keep the official ZIP boundary and write one processed file.
    counts = Counter(frame["category"])
    output = {
        "meta": {
            "title": "Greenpoint 2015 noise-related 311 requests",
            "source": "NYC 311 Service Requests 2010-2019 archive",
            "sourceRows": len(frame),
            "dateStart": "2015-01-01",
            "dateEnd": "2015-12-31",
            "zeroRequestDays": len(zero_days),
            "columns": ["id", "date", "weekday", "minute", "category", "latitude", "longitude"],
            "categoryCounts": dict(counts),
        },
        "days": all_days,
        "rows": compact_rows,
        "boundary": boundary,
    }
    OUTPUT_FILE.write_text(json.dumps(output, separators=(",", ":")))
    print(f"8. Processed file written: {OUTPUT_FILE}")
    print(f"   Processed size: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")

    # 9. Paste the processed real data into the single offline HTML file.
    template = TEMPLATE_FILE.read_text()
    embedded = json.dumps(output, separators=(",", ":")).replace("</", "<\\/")
    if "__EMBEDDED_DATA__" not in template:
        raise ValueError("The HTML template is missing its data placeholder.")
    INDEX_FILE.write_text(template.replace("__EMBEDDED_DATA__", embedded))
    print(f"9. Offline sandbox written: {INDEX_FILE}")
    print(f"   Sandbox size: {INDEX_FILE.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
