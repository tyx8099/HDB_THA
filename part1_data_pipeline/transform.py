"""Create unique resale identifiers from cleaned HDB resale records."""

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
    """Add a readable resale identifier and resolve duplicate base values."""
    missing = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Cleaned input is missing required columns: {sorted(missing)}")
    if {"resale_identifier", "resale_identifier_base"}.intersection(frame.columns):
        raise ValueError("Cleaned input already has a resale identifier column")

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
    source_record_number = pd.to_numeric(result["source_record_number"], errors="coerce")
    if (source_record_number.isna().any() or source_record_number.le(0).any()
            or source_record_number.mod(1).ne(0).any()
            or result["source_file"].eq("").any()):
        raise ValueError("Source lineage must contain a file name and positive record number")

    average_price = price.groupby([month, result["town"], result["flat_type"]]).transform("mean")
    average_component = average_price.astype(int).astype(str).str[:3]
    base_identifier = (
        "S"
        + result["block"].astype(str).map(block_component)
        + average_component
        + month.str[2:4]
        + month.str[5:7]
        + result["town"].astype(str).str[0]
    )
    order = pd.DataFrame({
        "base_identifier": base_identifier.to_numpy(),
        "source_file": result["source_file"].to_numpy(),
        "source_record_number": source_record_number.to_numpy(),
        "row_position": range(len(result)),
    }).sort_values(
        ["base_identifier", "source_file", "source_record_number", "row_position"], kind="stable"
    )
    order["sequence"] = order.groupby("base_identifier").cumcount() + 1
    sequence = order.set_index("row_position")["sequence"].reindex(range(len(result)))
    result["resale_identifier_base"] = base_identifier
    result["resale_identifier"] = base_identifier.where(
        sequence.eq(1), base_identifier + "-" + sequence.astype(str).str.zfill(3)
    )
    if result["resale_identifier"].duplicated().any():
        raise ValueError("Identifier collision resolution did not produce unique values")
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
    collisions = result["resale_identifier_base"].duplicated(keep=False)
    print(f"Wrote {len(result):,} transformed records to {args.output}")
    print(f"Resolved {collisions.sum():,} records across "
          f"{result.loc[collisions, 'resale_identifier_base'].nunique():,} colliding base identifiers")


if __name__ == "__main__":
    main()
