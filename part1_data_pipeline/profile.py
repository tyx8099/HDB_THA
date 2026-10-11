"""Generate a Markdown profile of the raw, master, and quarantined records."""

import argparse
import re
from pathlib import Path

import pandas as pd

from combine import REFERENCE_COLUMNS
from lease import remaining_lease
from price_anomalies import ANOMALY_COLUMNS, MIN_PEERS, ROBUST_Z_THRESHOLD, score_prices


PART1 = Path(__file__).parent
COMMON_FIELDS = (
    "month", "town", "flat_type", "block", "street_name", "storey_range",
    "floor_area_sqm", "flat_model", "lease_commence_date", "resale_price",
)
STOREY_PATTERN = re.compile(r"(\d+) TO (\d+)\Z")


def table(headers, rows):
    """Render a small Markdown table without another library dependency."""
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(map(cell, headers)) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(map(cell, row)) + " |" for row in rows)
    return "\n".join(lines)


def read_raw(raw_dir):
    frames = []
    inventory = []
    for path in sorted(raw_dir.glob("*.csv")):
        all_rows = 0
        in_scope = 0
        first_month = last_month = None
        columns = None
        for chunk in pd.read_csv(path, dtype=str, keep_default_na=False,
                                 encoding="utf-8-sig", chunksize=50_000):
            columns = list(chunk.columns)
            first_month = min(first_month or chunk["month"].min(), chunk["month"].min())
            last_month = max(last_month or chunk["month"].max(), chunk["month"].max())
            chunk["source_record_number"] = list(map(str, range(all_rows + 1, all_rows + len(chunk) + 1)))
            all_rows += len(chunk)
            selected = chunk.loc[chunk["month"].between("2012-01", "2017-12")].copy()
            if not selected.empty:
                selected["source_file"] = path.name
                frames.append(selected)
                in_scope += len(selected)
        inventory.append((path.name, all_rows, in_scope, len(columns), first_month, last_month))
    if not frames:
        raise ValueError(f"No in-scope CSV records found in {raw_dir}")
    inventory.sort(key=lambda item: item[4])
    return pd.concat(frames, ignore_index=True).fillna(""), inventory


def number(value):
    return f"{value:,.0f}"


def percent(numerator, denominator):
    if not denominator:
        return "n/a"
    value = 100 * numerator / denominator
    return "<0.1%" if 0 < value < 0.1 else f"{value:.1f}%"


def numeric_summary(frame):
    price = pd.to_numeric(frame["resale_price"], errors="coerce")
    area = pd.to_numeric(frame["floor_area_sqm"], errors="coerce")
    price_per_sqm = price / area.where(area.gt(0))
    return price, area, price_per_sqm


def storey_bounds(value):
    match = STOREY_PATTERN.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def failure_mechanism(row, widths, highest_reference_floor):
    """Explain the primary shape of a rejected row without changing its reason codes."""
    if "invalid_storey_range" not in row["quarantine_reasons"]:
        return "Flat model only"
    bounds = storey_bounds(row["storey_range"])
    if bounds is None:
        return "Unparseable storey band"
    lower, upper = bounds
    if upper - lower + 1 not in widths:
        return "Different storey-band width"
    if lower > highest_reference_floor:
        return "Above January 2012 floor coverage"
    return "Other storey value outside reference"


def generate(raw_dir, master_path, quarantine_path, cleaned_path):
    raw, inventory = read_raw(raw_dir)
    master = pd.read_csv(master_path, dtype=str, keep_default_na=False)
    quarantine = pd.read_csv(quarantine_path, dtype=str, keep_default_na=False)
    cleaned = pd.read_csv(cleaned_path, dtype=str, keep_default_na=False)

    # Reconcile by source position before reporting any derived statistics.
    key = ["source_file", "source_record_number"]
    raw_keys = set(map(tuple, raw[key].itertuples(index=False, name=None)))
    master_keys = set(map(tuple, master[key].itertuples(index=False, name=None)))
    quarantine_keys = set(map(tuple, quarantine[key].itertuples(index=False, name=None)))
    if (len(raw_keys) != len(raw) or len(master_keys) != len(master)
            or len(quarantine_keys) != len(quarantine)
            or master_keys & quarantine_keys or raw_keys != master_keys | quarantine_keys):
        raise ValueError("Raw, master, and quarantine source records do not reconcile")
    output_values = pd.concat([master, quarantine], ignore_index=True)
    compared = raw[key + list(COMMON_FIELDS) + ["remaining_lease"]].merge(
        output_values[key + list(COMMON_FIELDS) + ["remaining_lease"]],
        on=key, suffixes=("_raw", "_output"), validate="one_to_one",
    )
    for column in list(COMMON_FIELDS) + ["remaining_lease"]:
        if not compared[f"{column}_raw"].eq(compared[f"{column}_output"]).all():
            raise ValueError(f"Output value differs from source: {column}")
    cleaned_keys = set(map(tuple, cleaned[key].itertuples(index=False, name=None)))
    if len(cleaned_keys) != len(cleaned) or cleaned_keys != master_keys:
        raise ValueError("Cleaned records do not match the accepted master records")
    compared_cleaned = master.merge(cleaned, on=key, suffixes=("_master", "_cleaned"),
                                    validate="one_to_one")
    for column in master.columns.drop(key):
        if not compared_cleaned[f"{column}_master"].eq(
            compared_cleaned[f"{column}_cleaned"]
        ).all():
            raise ValueError(f"Cleaned output changed a master source value: {column}")
    expected_lease = cleaned["lease_commence_date"].map(remaining_lease)
    if (not cleaned["remaining_lease_2027_years"].eq(expected_lease.map(lambda value: str(value[0]))).all()
            or not cleaned["remaining_lease_2027_months"].eq(expected_lease.map(lambda value: str(value[1]))).all()
            or not cleaned["remaining_lease_2027"].eq(
                expected_lease.map(lambda value: f"{value[0]} years {value[1]:02d} months")
            ).all()):
        raise ValueError("Cleaned output has an incorrect as-of-2027 remaining lease")
    expected_anomalies = score_prices(cleaned)
    for column in ANOMALY_COLUMNS:
        if column not in cleaned or not cleaned[column].eq(expected_anomalies[column]).all():
            raise ValueError(f"Cleaned output has an incorrect price anomaly value: {column}")

    baseline = raw.loc[raw["month"].eq("2012-01")]
    reference = {column: set(baseline.loc[baseline[column].ne(""), column])
                 for column in REFERENCE_COLUMNS}
    for column in REFERENCE_COLUMNS:
        if not master[column].isin(reference[column]).all():
            raise ValueError(f"Master contains a value outside January 2012: {column}")

    common_duplicates = raw.duplicated(subset=list(COMMON_FIELDS), keep=False).sum()
    extra_duplicates = raw.duplicated(subset=list(COMMON_FIELDS), keep="first").sum()
    raw_price, raw_area, raw_ppsqm = numeric_summary(raw)
    master_price, _, master_ppsqm = numeric_summary(master)
    quarantine_price, _, quarantine_ppsqm = numeric_summary(quarantine)
    lease_year = pd.to_numeric(raw["lease_commence_date"], errors="coerce")
    transaction_year = pd.to_numeric(raw["month"].str[:4], errors="coerce")
    impossible_lease_years = int((lease_year.isna() | lease_year.gt(transaction_year)).sum())

    lines = [
        "# HDB resale data profiling report",
        "",
        "## Scope and method",
        "",
        "This report profiles the original files from the [HDB resale collection](https://data.gov.sg/collections/189/view), "
        "restricted to January 2012–December 2017, and the current master, cleaned, and quarantine outputs. "
        "Run `combine.py`, `lease.py`, and `price_anomalies.py` in that order before regenerating "
        "this report with `profile.py`. Source CSVs are never edited. "
        "The master is the set that passes the four exact January 2012 category checks; "
        "the quarantine contains failed records with reasons. Cleaned adds the as-of-2027 lease calculation "
        "and price anomaly review fields. "
        "Further transformations and hashing are pending.",
        "",
        "## 1. Source inventory",
        "",
        table(["Original CSV", "All rows", "2012–2017 rows", "Columns", "First month", "Last month"],
              [(name, number(total), number(selected), columns, first, last)
               for name, total, selected, columns, first, last in inventory]),
        "",
        f"The selected raw data contains **{number(len(raw))} records** over **{raw['month'].nunique()} months**. "
        "The first and last files include records outside the assessment period; they remain intact in `data/raw/`. "
        "The 2015–2016 and 2017-onward files add `remaining_lease`, giving them 11 columns instead of 10. "
        "The publication changes from approval date to registration date in March 2012, so trends across that "
        "boundary require care.",
        "",
        "## 2. Raw completeness and cardinality",
        "",
    ]

    completeness = []
    for column in list(COMMON_FIELDS) + ["remaining_lease"]:
        blanks = int(raw[column].eq("").sum())
        distinct = int(raw.loc[raw[column].ne(""), column].nunique())
        completeness.append((column, number(blanks), percent(blanks, len(raw)), number(distinct)))
    lines += [
        table(["Field", "Blank rows", "Blank share", "Distinct nonblank values"], completeness),
        "",
        f"The ten common source fields have **no blank values** in the selected period. "
        f"`remaining_lease` is blank for **{number(int(raw['remaining_lease'].eq('').sum()))} records** "
        "because their source files do not supply that column; this is schema absence, not an observed blank "
        "inside those files.",
        "",
        f"Across the ten common fields, **{number(common_duplicates)} rows** occur in repeated attribute "
        f"patterns (**{number(extra_duplicates)} rows** beyond the first occurrence). The source has no "
        "transaction ID, so matching published attributes alone cannot establish duplicate transactions.",
        "",
        "## 3. January 2012 authoritative values",
        "",
        f"The reference month has **{number(len(baseline))} records**. These exact values, with no case or "
        "spacing normalization, are the allowlists used by the current merge step:",
        "",
        table(["Field", "Allowed values", "Values"],
              [(column, len(reference[column]), ", ".join(sorted(reference[column])))
               for column in REFERENCE_COLUMNS]),
        "",
    ]

    unseen_rows = []
    for column in REFERENCE_COLUMNS:
        unseen = raw.loc[~raw[column].isin(reference[column]), column].value_counts()
        unseen_rows.append((column, number(int(unseen.sum())), len(unseen),
                            ", ".join(f"{value} ({number(count)})" for value, count in unseen.head(6).items()) or "None"))
    lines += [
        table(["Field", "Rows outside reference", "New values", "Most frequent new values"], unseen_rows),
        "",
        "## 4. Lifecycle reconciliation",
        "",
        table(["Output", "Records", "Share of selected raw"], [
            ("Selected raw", number(len(raw)), "100.0%"),
            ("Master", number(len(master)), percent(len(master), len(raw))),
            ("Cleaned", number(len(cleaned)), percent(len(cleaned), len(raw))),
            ("Quarantined", number(len(quarantine)), percent(len(quarantine), len(raw))),
        ]),
        "",
        "Every selected raw record appears exactly once across master and quarantine, based on source file "
        "and source record number. The two outputs have no overlapping lineage keys, and all source "
        "field values match the original CSV records. Cleaned has the same accepted records and original "
        "field values as master, plus derived lease and price anomaly columns; it is a downstream copy, so its rows "
        "are not added again to the raw reconciliation total.",
        "",
    ]

    source_counts = raw.groupby("source_file").size().rename("raw")
    master_counts = master.groupby("source_file").size().rename("master")
    quarantine_counts = quarantine.groupby("source_file").size().rename("quarantine")
    source_stages = pd.concat([source_counts, master_counts, quarantine_counts], axis=1).fillna(0).astype(int)
    source_stages = source_stages.reindex([item[0] for item in inventory])
    lines += [
        table(["Source file", "Selected raw", "Master", "Quarantined", "Quarantine share"],
              [(name, number(row["raw"]), number(row["master"]), number(row["quarantine"]),
                percent(row["quarantine"], row["raw"])) for name, row in source_stages.iterrows()]),
        "",
    ]

    raw_year = raw.groupby(raw["month"].str[:4]).size()
    master_year = master.groupby(master["month"].str[:4]).size()
    quarantine_year = quarantine.groupby(quarantine["month"].str[:4]).size()
    lines += [
        table(["Year", "Selected raw", "Master", "Quarantined", "Quarantine share"],
              [(year, number(raw_year[year]), number(master_year.get(year, 0)),
                number(quarantine_year.get(year, 0)), percent(quarantine_year.get(year, 0), raw_year[year]))
               for year in sorted(raw_year.index)]),
        "",
        "## 5. Quarantine profile",
        "",
    ]

    reasons = quarantine["quarantine_reasons"].str.split("|", regex=False).explode().value_counts()
    combinations = quarantine["quarantine_reasons"].value_counts()
    lines += [
        table(["Failed rule", "Rows"], [(reason, number(count)) for reason, count in reasons.items()]),
        "",
        "A row may fail more than one rule, so the rule counts can sum to more than the number of "
        "quarantined records. Distinct reason combinations are:",
        "",
        table(["Reason combination", "Rows"], [(reason, number(count)) for reason, count in combinations.items()]),
        "",
    ]

    reference_bounds = [storey_bounds(value) for value in reference["storey_range"]]
    if any(bounds is None for bounds in reference_bounds):
        raise ValueError("January 2012 has an unparseable storey range")
    widths = {upper - lower + 1 for lower, upper in reference_bounds}
    highest_reference_floor = max(upper for _, upper in reference_bounds)
    mechanisms = quarantine.apply(
        failure_mechanism, axis=1,
        args=(widths, highest_reference_floor),
    )
    mechanism_counts = mechanisms.value_counts()
    lines += [
        "### Why the rows fail",
        "",
        f"January 2012 storey bands each span **{', '.join(map(str, sorted(widths)))} floors** "
        f"and end at floor **{highest_reference_floor}**. Classifying each quarantined row by its "
        "primary mismatch gives:",
        "",
        table(["Failure mechanism", "Rows", "Share of quarantine"],
              [(mechanism, number(count), percent(count, len(quarantine)))
               for mechanism, count in mechanism_counts.items()]),
        "",
    ]

    unexpected_rows = []
    for column in ("storey_range", "flat_model"):
        failed = quarantine.loc[quarantine["quarantine_reasons"].str.contains(
            f"invalid_{column}", regex=False
        )]
        for value, group in failed.groupby(column):
            unexpected_rows.append((column, value, len(group), group["month"].min(), group["month"].max()))
    unexpected_rows.sort(key=lambda item: (item[0], -item[2], item[1]))
    lines += [
        table(["Field", "Value absent in January 2012", "Rows", "First month", "Last month"],
              [(column, value, number(count), first, last)
               for column, value, count, first, last in unexpected_rows]),
        "",
    ]

    width_rows = quarantine.loc[mechanisms.eq("Different storey-band width")]
    width_months = ", ".join(sorted(width_rows["month"].unique()))
    high_rows = quarantine.loc[mechanisms.eq("Above January 2012 floor coverage")]
    both_count = int(quarantine["quarantine_reasons"].eq(
        "invalid_flat_model|invalid_storey_range").sum())
    lines += [
        f"The **{number(len(width_rows))} different-width rows** occur in **{width_months}**. "
        "Their five-floor bands (`01 TO 05`, `06 TO 10`, etc.) do not exactly match January's "
        "three-floor bands. This is a temporary source coding difference, not evidence that all "
        "those sales are invalid. "
        f"The **{number(len(high_rows))} higher-floor rows** use three-floor bands above floor "
        f"{highest_reference_floor}; the first such row appears in **{high_rows['month'].min()}**. "
        f"**{number(both_count)} rows** fail both storey and flat-model checks, so the two "
        "field-level failure totals overlap.",
        "",
    ]

    raw_month = raw.groupby("month").size()
    master_month = master.groupby("month").size()
    quarantine_month = quarantine.groupby("month").size()
    empty_master_months = [month for month in raw_month.index if master_month.get(month, 0) == 0]
    lines += [
        f"**Months with no accepted records:** {', '.join(sorted(empty_master_months)) or 'None'}. "
        "In March–May 2012, the registration-date source uses storey bands such as `01 TO 05` and "
        "`06 TO 10`; January 2012 uses `01 TO 03`, `04 TO 06`, and similar three-floor bands. "
        "The strict reference rule therefore quarantines every record in those three months. "
        "Quarantine means a rule failed; it does not prove the sale or source value is erroneous.",
        "",
        "## 6. Numeric behaviour",
        "",
        table(["Measure", "Invalid or unavailable rows", "Minimum", "Median", "99th percentile", "Maximum"], [
            ("Raw resale price (SGD)", number(int((raw_price.isna() | raw_price.le(0)).sum())), number(raw_price.min()),
             number(raw_price.median()), number(raw_price.quantile(.99)), number(raw_price.max())),
            ("Raw floor area (sqm)", number(int((raw_area.isna() | raw_area.le(0)).sum())),
             f"{raw_area.min():.2f}", f"{raw_area.median():.2f}",
             f"{raw_area.quantile(.99):.2f}", f"{raw_area.max():.2f}"),
            ("Raw price per sqm (SGD)", number(int(raw_ppsqm.isna().sum())),
             number(raw_ppsqm.min()), number(raw_ppsqm.median()),
             number(raw_ppsqm.quantile(.99)), number(raw_ppsqm.max())),
        ]),
        "",
        table(["Bucket", "Median resale price (SGD)", "Median price per sqm (SGD)"], [
            ("Master", number(master_price.median()), number(master_ppsqm.median())),
            ("Quarantined", number(quarantine_price.median()), number(quarantine_ppsqm.median())),
        ]),
        "",
        f"Lease commencement years range from **{int(lease_year.min())}** to **{int(lease_year.max())}**. "
        f"There are **{number(impossible_lease_years)}** non-numeric commencement years or years later "
        "than their transaction year.",
        "",
        "### Remaining lease on 1 January 2027",
        "",
        "The source records `lease_commence_date` as a year. Assuming commencement on 1 January of that "
        "year and a 99-year term, the cleaned output has the following derived values:",
        "",
        table(["Metric", "Value"], [
            ("Cleaned records", number(len(cleaned))),
            ("Minimum full years remaining", cleaned["remaining_lease_2027_years"].astype(int).min()),
            ("Maximum full years remaining", cleaned["remaining_lease_2027_years"].astype(int).max()),
            ("Records with a nonzero month component", number(int(cleaned["remaining_lease_2027_months"].ne("0").sum()))),
            ("Records retaining a nonblank source remaining_lease", number(int(cleaned["remaining_lease"].ne("").sum()))),
        ]),
        "",
        "Because both the assumed lease start and the requested as-of date are 1 January, all calculated "
        "month components are zero. The source does not give a commencement month, so actual month "
        "precision cannot be recovered. The source `remaining_lease` field is measured at a different "
        "date and is preserved unchanged, not used in this calculation.",
        "",
        "### Potential resale price anomalies",
        "",
        "For each accepted record, calculate resale price divided by floor area (SGD/sqm), then compare "
        "its log value with transactions in the same **calendar year, town, and flat type**. The robust "
        "score is `0.6745 × (log(price/sqm) − peer median) / peer MAD`, where MAD is the median "
        "absolute deviation. A score above +3.5 is `high`; below −3.5 is `low`. Groups need at "
        f"least {MIN_PEERS} records and nonzero MAD. Each record is included in its own peer group.",
        "",
        table(["Status", "Rows", "Share of cleaned"], [
            (status, number(int((cleaned["price_anomaly_status"] == status).sum())),
             percent(int((cleaned["price_anomaly_status"] == status).sum()), len(cleaned)))
            for status in ("high", "low", "normal", "insufficient_peers", "zero_mad", "invalid_numeric")
        ]),
        "",
        f"The cutoff is ±{ROBUST_Z_THRESHOLD}. The `price_anomaly_flag` is true only for high and low scores. "
        "Unassessed rows remain explicitly marked. All records stay in cleaned output; these are "
        "review leads, not proven data errors. Flat age, exact floor, model, and other property "
        "differences are not controlled by this heuristic and may explain unusual prices.",
        "",
        table(["Direction", "Month", "Town", "Flat type", "Price (SGD)", "Area (sqm)",
               "SGD/sqm", "Robust score"], [
            (direction, row["month"], row["town"], row["flat_type"], row["resale_price"],
             row["floor_area_sqm"], row["price_per_sqm"], row["price_anomaly_robust_z"])
            for direction, ascending in (("High", False), ("Low", True))
            for _, row in cleaned.loc[cleaned["price_anomaly_status"].eq(direction.lower())].sort_values(
                "price_anomaly_robust_z", key=lambda series: pd.to_numeric(series), ascending=ascending
            ).head(3).iterrows()
        ]),
        "",
        "## 7. Monthly reconciliation",
        "",
        table(["Month", "Selected raw", "Master", "Quarantined", "Quarantine share"],
              [(month, number(raw_month[month]), number(master_month.get(month, 0)),
                number(quarantine_month.get(month, 0)),
                percent(quarantine_month.get(month, 0), raw_month[month]))
               for month in sorted(raw_month.index)]),
        "",
        "## Assumptions and follow-up",
        "",
        "- January 2012 observed values are used as exact allowlists because the assessment calls them "
        "strictly authoritative. Newly introduced but plausible later values are quarantined.",
        "- The 2015-onward source `remaining_lease` is measured at the resale application, not as of "
        "1 January 2027. The new value assumes a 1 January lease start because only the commencement "
        "year is available.",
        "- Repeated attribute patterns are not removed pending a defensible duplicate rule.",
        "- This profile covers raw, master, cleaned, and quarantine. Extend it after producing transformed "
        "and hashed outputs so the final report covers the complete pipeline lifecycle.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=PART1 / "data" / "raw")
    parser.add_argument("--master", type=Path, default=PART1 / "data" / "master" / "resale_master_2012_2017.csv")
    parser.add_argument("--quarantine", type=Path, default=PART1 / "data" / "quarantined" / "resale_quarantined_2012_2017.csv")
    parser.add_argument("--cleaned", type=Path, default=PART1 / "data" / "cleaned" / "resale_cleaned_2012_2017.csv")
    parser.add_argument("--output", type=Path, default=PART1 / "DATA_PROFILING_REPORT.md")
    args = parser.parse_args()
    report = generate(args.raw_dir, args.master, args.quarantine, args.cleaned)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
