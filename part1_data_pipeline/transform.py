"""Create a resale identifier from cleaned HDB resale records.

The script writes the derived identifier and reports any duplicate values.
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from lease import DEFAULT_CLEANED


PART1 = Path(__file__).parent
DEFAULT_OUTPUT = PART1 / "data" / "transformed" / "resale_transformed_2012_2017.csv"
REQUIRED_COLUMNS = (
    "month", "town", "flat_type", "block", "resale_price",
    "source_file", "source_record_number",
)


def block_component(block):
    """Return the first three block digits, padded on the left when needed."""
    digits = re.sub(r"\D", "", block)
    if not digits:
        raise ValueError(f"Block has no digits: {block!r}")
    return digits[:3].zfill(3)


def transform(frame):
    """Add a readable, possibly non-unique resale identifier to cleaned records."""
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Cleaned input is missing required columns: {sorted(missing)}")
    if "resale_identifier" in frame.columns:
        raise ValueError("Cleaned input already has resale_identifier")

    result = frame.copy()
    month = result["month"].astype(str)
    parsed_month = pd.to_datetime(month + "-01", format="%Y-%m-%d", errors="coerce")
    if not (month.str.fullmatch(r"\d{4}-\d{2}") & parsed_month.notna()).all():
        raise ValueError("All month values must use YYYY-MM")
    price = pd.to_numeric(result["resale_price"], errors="coerce")
    if price.isna().any() or price.le(0).any():
        raise ValueError("All resale_price values must be positive numbers")
    if result["town"].eq("").any() or result["flat_type"].eq("").any():
        raise ValueError("Town and flat_type must be nonblank")

    average_price = price.groupby([month, result["town"], result["flat_type"]]).transform("mean")
    average_component = average_price.astype(int).astype(str).str[:3]
    result["resale_identifier"] = (
        "S"
        + result["block"].astype(str).map(block_component)
        + average_component
        + month.str[2:4]
        + month.str[5:7]
        + result["town"].astype(str).str[0]
    )
    return result


def build_transformed(input_path=DEFAULT_CLEANED, output_path=DEFAULT_OUTPUT):
    """Read cleaned data, write the transformed dataset atomically, and return it."""
    frame = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    result = transform(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".partial")
    try:
        result.to_csv(temporary, index=False, lineterminator="\n")
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEANED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_transformed(args.input, args.output)
    collisions = result["resale_identifier"].duplicated(keep=False)
    print(f"Wrote {len(result):,} transformed records to {args.output}")
    print(f"Base identifier collisions: {collisions.sum():,} records across "
          f"{result.loc[collisions, 'resale_identifier'].nunique():,} identifiers")


if __name__ == "__main__":
    main()
