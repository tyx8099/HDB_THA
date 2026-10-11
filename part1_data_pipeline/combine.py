"""Combine HDB CSVs using the starting month as a strict category reference."""

import argparse
import csv
import re
from collections import Counter
from datetime import date
from pathlib import Path


DEFAULT_RAW_DIR = Path(__file__).parent / "data" / "raw"
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "master" / "resale_master_2012_2017.csv"
DEFAULT_QUARANTINE = Path(__file__).parent / "data" / "quarantined" / "resale_quarantined_2012_2017.csv"
MONTH_PATTERN = re.compile(r"\d{4}-\d{2}\Z")
LINEAGE_COLUMNS = ("source_file", "source_record_number")
REFERENCE_COLUMNS = ("town", "flat_type", "flat_model", "storey_range")


def parse_month(value: str) -> date:
    if not MONTH_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid month: {value!r}")
    return date.fromisoformat(f"{value}-01")


def month_range(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year, month = year + 1, 1


def inspect_source(path: Path, start: date, end: date):
    months = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        if not columns or "month" not in columns or len(columns) != len(set(columns)):
            raise ValueError(f"Invalid CSV header in {path}")
        if any(column in columns for column in LINEAGE_COLUMNS):
            raise ValueError(f"Source header conflicts with lineage columns in {path}")
        for record_number, row in enumerate(reader, start=1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row {record_number} in {path}")
            month = parse_month(row["month"])
            if start <= month <= end:
                months.add(row["month"])
    return columns, months


def combine(raw_dir: Path, output: Path, quarantine: Path, start: date, end: date) -> Counter:
    if start > end:
        raise ValueError("Start month must be on or before end month")
    sources = sorted(raw_dir.glob("*.csv"))
    if not sources:
        raise ValueError(f"No CSV files found in {raw_dir}")

    inspected = []
    for path in sources:
        columns, months = inspect_source(path, start, end)
        if months:
            inspected.append((path, columns, months))

    expected_months = set(month_range(start, end))
    found_months = set().union(*(months for _, _, months in inspected))
    missing_months = sorted(expected_months - found_months)
    if missing_months:
        raise ValueError(f"Missing months in source files: {', '.join(missing_months)}")

    baseline_sources = [item for item in inspected if f"{start:%Y-%m}" in item[2]]
    if len(baseline_sources) != 1:
        raise ValueError("Expected exactly one source file for the starting month")
    baseline_path, baseline_columns, _ = baseline_sources[0]
    if not set(REFERENCE_COLUMNS).issubset(baseline_columns):
        raise ValueError(f"Missing authoritative columns in {baseline_path}")
    reference = {column: set() for column in REFERENCE_COLUMNS}
    with baseline_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if row["month"] == f"{start:%Y-%m}":
                for column in REFERENCE_COLUMNS:
                    if row[column]:
                        reference[column].add(row[column])
    if any(not values for values in reference.values()):
        raise ValueError("Starting month has no authoritative values for a required column")

    columns = list(baseline_columns)
    for _, source_columns, _ in inspected:
        for column in source_columns:
            if column not in columns:
                columns.append(column)
    columns.extend(LINEAGE_COLUMNS)

    inspected.sort(key=lambda item: (min(item[2]), item[0].name))
    if output == quarantine:
        raise ValueError("Master and quarantine outputs must be different files")
    output.parent.mkdir(parents=True, exist_ok=True)
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    quarantine_temporary = quarantine.with_suffix(quarantine.suffix + ".partial")
    counts = Counter()
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle, quarantine_temporary.open(
            "w", newline="", encoding="utf-8"
        ) as quarantine_handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            quarantine_writer = csv.DictWriter(
                quarantine_handle, fieldnames=columns + ["quarantine_reasons"], lineterminator="\n"
            )
            writer.writeheader()
            quarantine_writer.writeheader()
            for path, _, _ in inspected:
                with path.open(newline="", encoding="utf-8-sig") as source:
                    for record_number, row in enumerate(csv.DictReader(source), start=1):
                        month = parse_month(row["month"])
                        if start <= month <= end:
                            output_row = {column: row.get(column, "") for column in columns}
                            output_row["source_file"] = path.name
                            output_row["source_record_number"] = record_number
                            reasons = [
                                f"invalid_{column}"
                                for column in REFERENCE_COLUMNS
                                if not row.get(column) or row[column] not in reference[column]
                            ]
                            if reasons:
                                output_row["quarantine_reasons"] = "|".join(reasons)
                                quarantine_writer.writerow(output_row)
                                counts["quarantined"] += 1
                            else:
                                writer.writerow(output_row)
                                counts["accepted"] += 1
        temporary.replace(output)
        quarantine_temporary.replace(quarantine)
    finally:
        temporary.unlink(missing_ok=True)
        quarantine_temporary.unlink(missing_ok=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--quarantine-output", type=Path, default=DEFAULT_QUARANTINE)
    parser.add_argument("--start", default="2012-01", help="First month, YYYY-MM")
    parser.add_argument("--end", default="2017-12", help="Last month, YYYY-MM")
    args = parser.parse_args()
    counts = combine(
        args.raw_dir, args.output, args.quarantine_output, parse_month(args.start), parse_month(args.end)
    )
    print(f"Master: {counts['accepted']:,} records in {args.output}")
    print(f"Quarantined: {counts['quarantined']:,} records in {args.quarantine_output}")


if __name__ == "__main__":
    main()
