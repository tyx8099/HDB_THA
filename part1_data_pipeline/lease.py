"""Add remaining lease as of a fixed date to the validated master records."""

import argparse
import csv
from datetime import date
from pathlib import Path


PART1 = Path(__file__).parent
DEFAULT_MASTER = PART1 / "data" / "master" / "resale_master_2012_2017.csv"
DEFAULT_CLEANED = PART1 / "data" / "cleaned" / "resale_cleaned_2012_2017.csv"
DEFAULT_AS_OF = date(2027, 1, 1)
NEW_COLUMNS = (
    "remaining_lease_2027_years",
    "remaining_lease_2027_months",
    "remaining_lease_2027",
)


def remaining_lease(commencement_year: str, as_of: date = DEFAULT_AS_OF) -> tuple[int, int]:
    """Count full calendar months until a 99-year lease ends.

    The source supplies only the commencement year, so the lease is assumed to
    begin on 1 January of that year. Expired leases are clamped to zero.
    """
    if len(commencement_year) != 4 or not commencement_year.isdigit():
        raise ValueError(f"Expected a four-digit lease commencement year: {commencement_year!r}")
    year = int(commencement_year)
    if year > as_of.year or year + 99 > 9999:
        raise ValueError(f"Implausible lease commencement year: {commencement_year!r}")
    lease_end = date(year + 99, 1, 1)
    if as_of >= lease_end:
        return 0, 0
    full_months = (lease_end.year - as_of.year) * 12 + lease_end.month - as_of.month
    if as_of.day > lease_end.day:
        full_months -= 1
    return divmod(full_months, 12)


def build_cleaned(master: Path, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    count = 0
    try:
        with master.open(newline="", encoding="utf-8") as source, temporary.open(
            "w", newline="", encoding="utf-8"
        ) as destination:
            reader = csv.DictReader(source)
            if not reader.fieldnames or "lease_commence_date" not in reader.fieldnames:
                raise ValueError("Master dataset has no lease_commence_date column")
            if any(column in reader.fieldnames for column in NEW_COLUMNS):
                raise ValueError("Master dataset already has derived lease columns")
            writer = csv.DictWriter(
                destination, fieldnames=reader.fieldnames + list(NEW_COLUMNS),
                lineterminator="\n",
            )
            writer.writeheader()
            for row in reader:
                years, months = remaining_lease(row["lease_commence_date"])
                row["remaining_lease_2027_years"] = years
                row["remaining_lease_2027_months"] = months
                row["remaining_lease_2027"] = f"{years} years {months:02d} months"
                writer.writerow(row)
                count += 1
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_CLEANED)
    args = parser.parse_args()
    count = build_cleaned(args.master, args.output)
    print(f"Added remaining lease as of {DEFAULT_AS_OF} for {count:,} records")


if __name__ == "__main__":
    main()
